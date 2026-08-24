"""Unit tests for the catalog promote mapping.

The DB write path needs Postgres and is covered by the integration pass; what
is unit-testable is the part that decides what gets written: reading an item
from the mirror and flattening it onto layer columns.
"""

from pathlib import Path

import duckdb
import pytest
from goatlib.tools.catalog_promote import (
    CatalogItemNotFoundError,
    _jsonable,
    layer_type,
    read_item,
)


@pytest.fixture()
def mirror(tmp_path: Path) -> Path:
    """A minimal mirror_items.parquet with the columns promote reads."""
    out = tmp_path / "mirror_items.parquet"
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
            SELECT * FROM (VALUES
                ('item-1', 'Schulstandorte Bayern', 'Alle Schulen',
                 'CC-BY-4.0', 'places', 'LDBV', ['schulen', 'bildung'],
                 'de', '2024-11', '../../../data/item-1.parquet',
                 'feature', 'point', 'harvested from ...',
                 TIMESTAMP '2024-01-01', 9.5, 47.2, 13.9, 50.6,
                 [{{'rel': 'via', 'href': 'https://geodaten.bayern.de/x'}}],
                 NULL),
                ('item-2', 'Statistik ohne Geometrie', NULL,
                 'not-a-license', 'nonsense-category', NULL, [],
                 'German', '3', 'data/item-2.parquet',
                 'table', NULL, NULL,
                 NULL, NULL, NULL, NULL, NULL,
                 [], NULL)
            ) AS t(
                id, title, description, license, category, publisher,
                keywords, language_code, version, parquet_url,
                "goat:layerType", "goat:geometryType", "processing:lineage",
                datetime_start, bbox_xmin, bbox_ymin, bbox_xmax, bbox_ymax,
                links, assets
            )
        ) TO '{out}' (FORMAT PARQUET)
        """
    )
    con.close()
    return out


def test_read_item_returns_row_as_dict(mirror: Path) -> None:
    item = read_item(mirror, "item-1")
    assert item["title"] == "Schulstandorte Bayern"
    assert item["version"] == "2024-11"
    assert item["goat:geometryType"] == "point"


def test_read_item_unknown_id_raises(mirror: Path) -> None:
    with pytest.raises(CatalogItemNotFoundError):
        read_item(mirror, "no-such-item")


def test_jsonable_snapshot_serialises_timestamps(mirror: Path) -> None:
    """The snapshot must survive json.dumps — timestamps become ISO strings."""
    import json

    snap = _jsonable(read_item(mirror, "item-1"))
    json.dumps(snap)  # raises on anything non-serialisable
    assert snap["license"] == "CC-BY-4.0"  # raw contract value, unmapped
    assert snap["datetime_start"].startswith("2024-01-01")


def test_layer_type_geometry_wins(mirror: Path) -> None:
    assert layer_type(read_item(mirror, "item-1")) == ("feature", "point")


def test_layer_type_no_geometry_is_a_table(mirror: Path) -> None:
    assert layer_type(read_item(mirror, "item-2")) == ("table", None)


def test_bucket_key_resolves_relative_hrefs() -> None:
    """Contract C8: published hrefs are tree-relative; only the basename and
    the bucket's fixed data/ prefix identify the object."""
    from goatlib.tools.catalog_materialize import bucket_key_for

    assert bucket_key_for("../../../data/ab-12.parquet") == "data/ab-12.parquet"
    assert bucket_key_for("data/x.parquet") == "data/x.parquet"


def test_bucket_key_rejects_non_parquet() -> None:
    import pytest as _pytest
    from goatlib.tools.catalog_materialize import bucket_key_for

    with _pytest.raises(ValueError):
        bucket_key_for("styles/ab-12.json")
    with _pytest.raises(ValueError):
        bucket_key_for("")
