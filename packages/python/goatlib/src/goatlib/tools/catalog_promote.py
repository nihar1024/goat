"""Promote a catalog item into a shared, read-only ``customer.layer``.

The catalog's source of truth is the STAC mirror on the shared volume
(``mirror_items.parquet``); nothing about a harvested dataset lives in
Postgres until someone uses it. The first add-to-project promotes the item:
one layer row, owned by the catalog system user, shared by every user and
org that adds the same item at the same version.

The row carries only what rendering needs — name, description, type,
geometry type, extent, style. Everything else the item says about itself
(license, publisher, keywords, ...) is stored verbatim in
``other_properties.catalog_item``: the mirror is rebuilt wholesale on every
sync, so a superseded version's metadata exists nowhere else afterwards.
The legacy flat metadata columns are left NULL — the catalog UI reads the
STAC service and the snapshot, not those columns.

Identity is ``(catalog_external_uid, catalog_version)`` under a partial
unique index — the idempotency and race mechanism. A concurrent promote of
the same item conflicts on the index; the loser reads the winner's row.

Data is NOT copied here. The layer row is created with materialize status
``pending`` and the caller enqueues the materialize job; the layer becomes
drawable when that finishes.
"""

from __future__ import annotations

import json
import uuid as uuid_module
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import duckdb

_ITEM_COLUMNS = [
    "id",
    "title",
    "description",
    "license",
    "category",
    "publisher",
    "keywords",
    "language_code",
    "version",
    "parquet_url",
    '"goat:layerType"',
    '"goat:geometryType"',
    '"processing:lineage"',
    "datetime_start",
    "bbox_xmin",
    "bbox_ymin",
    "bbox_xmax",
    "bbox_ymax",
    "links",
    "assets",
]


class CatalogItemNotFoundError(ValueError):
    """The mirror has no item with this id."""


def read_item(mirror_items_path: str | Path, item_id: str) -> dict[str, Any]:
    """One item row from the mirror, as a plain dict keyed by column name."""
    con = duckdb.connect()
    try:
        cols = ", ".join(_ITEM_COLUMNS)
        row = con.execute(
            f"SELECT {cols} FROM read_parquet(?) WHERE id = ?",
            [str(mirror_items_path), item_id],
        ).fetchone()
        if row is None:
            raise CatalogItemNotFoundError(f"Catalog item not found: {item_id}")
        names = [c.strip('"') for c in _ITEM_COLUMNS]
        return dict(zip(names, row))
    finally:
        con.close()


def resolve_item_ids(
    mirror_items_path: str | Path, catalog_ids: list[str]
) -> list[str]:
    """The item ids named by `catalog_ids`, expanding any dataset id among them.

    A caller names what it picked, and what a user picks in the catalog is a
    *dataset* — a Collection. Promotion is per Item, and a Collection's id is
    not one of its items' ids (the harvester mints a separate uuid for each),
    so a dataset id has to be resolved to the layers inside it. A single-layer
    dataset resolves to its one item; a bundle to all of its members, which is
    what adding it means.

    Request order is preserved, and an id already covered by an earlier one is
    dropped: ticking a bundle and one of its layers is one request for that
    layer, not two entries in the project.
    """
    if not catalog_ids:
        return []

    con = duckdb.connect()
    try:
        placeholders = ", ".join("?" * len(catalog_ids))
        rows = con.execute(
            f"""
            SELECT id, collection FROM read_parquet(?)
            WHERE id IN ({placeholders}) OR collection IN ({placeholders})
            ORDER BY id
            """,
            [str(mirror_items_path), *catalog_ids, *catalog_ids],
        ).fetchall()
    finally:
        con.close()

    items = {row[0] for row in rows}
    members: dict[str, list[str]] = {}
    for item_id, collection_id in rows:
        if collection_id is not None:
            members.setdefault(collection_id, []).append(item_id)

    resolved: list[str] = []
    seen: set[str] = set()
    for catalog_id in catalog_ids:
        if catalog_id in items:
            expanded = [catalog_id]
        elif catalog_id in members:
            expanded = members[catalog_id]
        else:
            raise CatalogItemNotFoundError(f"Catalog item not found: {catalog_id}")
        for item_id in expanded:
            if item_id not in seen:
                seen.add(item_id)
                resolved.append(item_id)
    return resolved


def layer_type(item: dict[str, Any]) -> tuple[str, str | None]:
    """(layer type, geometry type) for the layer row.

    ``goat:geometryType`` absent means an attribute table (contract §3.1).
    """
    geom = item.get("goat:geometryType")
    declared = (item.get("goat:layerType") or "").lower()
    if geom:
        return "feature", str(geom).lower()
    if declared in ("table", "feature", "raster"):
        return declared, None
    return "table", None


def _jsonable(item: dict[str, Any]) -> dict[str, Any]:
    """The item with every value JSON-serialisable (timestamps to ISO)."""

    def conv(v: Any) -> Any:
        if hasattr(v, "isoformat"):
            return v.isoformat()
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v

    return {k: conv(v) for k, v in item.items()}


def _default_style(geometry_type: str | None) -> dict[str, Any]:
    from goatlib.tools.style import get_default_style

    return dict(get_default_style(geometry_type))


async def promote(
    conn: asyncpg.Connection,
    item_id: str,
    *,
    mirror_items_path: str | Path,
    owner_id: uuid_module.UUID,
    folder_id: uuid_module.UUID,
    schema: str = "customer",
) -> dict[str, Any]:
    """Return the shared ``customer.layer`` for a catalog item, creating it
    if this is the first use of this (item, version).

    Race-safe via the partial unique index on
    ``(catalog_external_uid, catalog_version)``: the INSERT is
    ``ON CONFLICT DO NOTHING``, and when it inserts no row the winner's is
    read back. Returns ``{"layer_id", "created", "parquet_url"}``.
    """
    item = read_item(mirror_items_path, item_id)
    version = str(item.get("version") or "")

    # UPDATE, not SELECT: touching updated_at moves a reused layer out of the
    # catalog-GC grace window, so re-adding a long-unreferenced layer can't be
    # swept between here and the project-link creation.
    existing = await conn.fetchrow(
        f"""
        UPDATE {schema}.layer SET updated_at = NOW()
        WHERE catalog_external_uid = $1 AND catalog_version = $2
        RETURNING id
        """,
        item_id,
        version,
    )
    if existing:
        return {
            "layer_id": str(existing["id"]),
            "created": False,
            "parquet_url": item.get("parquet_url"),
        }

    ltype, geom_type = layer_type(item)
    style = _default_style(geom_type) if geom_type else {}
    if style:
        style.setdefault("visibility", True)
    name = (item.get("title") or "").strip() or item_id
    other_properties = {
        "catalog_materialize": {"status": "pending"},
        "catalog_item": _jsonable(item),
    }

    has_bbox = all(
        item.get(k) is not None
        for k in ("bbox_xmin", "bbox_ymin", "bbox_xmax", "bbox_ymax")
    )

    new_id = uuid_module.uuid4()
    inserted = await conn.fetchrow(
        f"""
        INSERT INTO {schema}.layer (
            id, user_id, folder_id, name, description, type,
            feature_layer_type, feature_layer_geometry_type, extent,
            properties, other_properties,
            in_catalog, catalog_external_uid, catalog_version,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            CASE WHEN $6 = 'feature' THEN 'standard' ELSE NULL END,
            $7,
            CASE WHEN $8 THEN
                ST_Multi(ST_MakeEnvelope($9, $10, $11, $12, 4326))
            END,
            $13::jsonb, $14::jsonb,
            FALSE, $15, $16,
            NOW(), NOW()
        )
        ON CONFLICT (catalog_external_uid, catalog_version)
            WHERE catalog_external_uid IS NOT NULL
        DO NOTHING
        RETURNING id
        """,
        new_id,
        owner_id,
        folder_id,
        name,
        item.get("description"),
        ltype,
        geom_type,
        has_bbox,
        item.get("bbox_xmin"),
        item.get("bbox_ymin"),
        item.get("bbox_xmax"),
        item.get("bbox_ymax"),
        json.dumps(style),
        json.dumps(other_properties),
        item_id,
        version,
    )

    if inserted is None:
        # Same reasoning as the fast path: bump updated_at so a concurrent
        # promote that lost the race still leaves the winner outside the GC
        # grace window.
        winner = await conn.fetchrow(
            f"""
            UPDATE {schema}.layer SET updated_at = NOW()
            WHERE catalog_external_uid = $1 AND catalog_version = $2
            RETURNING id
            """,
            item_id,
            version,
        )
        if winner is None:
            raise RuntimeError(
                f"Promote of {item_id}@{version} conflicted but no winner row "
                f"is visible; retry"
            )
        return {
            "layer_id": str(winner["id"]),
            "created": False,
            "parquet_url": item.get("parquet_url"),
        }

    return {
        "layer_id": str(new_id),
        "created": True,
        "parquet_url": item.get("parquet_url"),
    }
