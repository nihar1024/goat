"""Writes an edge batch and its derived nodes, keyed on the `id` column.

Not ``feature_write_service``: that addresses rows by rowid, and a batch that
deletes rows shifts the rowids of rows it has not touched yet. The editor's
feature ids (``rowid + 1``, as the tiles hand them out) are resolved to the
layer's own ``id`` values once, up front, and every write after that keys on
``id``.

Candidate geometry is handed out in EPSG:3857 metres so ``goatlib.bundles.topology``
can measure a tolerance in metres. Writes go back as 4326: a split is applied as a
fraction along the stored line, and a node minted on that line comes from
``ST_LineInterpolatePoint``, so the node sits exactly on the geometry rather than
near it.
"""

import json
import logging
import uuid
from typing import Any, Iterable, Sequence

from goatlib.bundles.topology import EdgeCandidate, NodeCandidate
from shapely import wkt

# One definition of the rowid convention: a public feature id is rowid + 1,
# because MapLibre treats MVT feature id 0 as "unset".
from geoapi.services.feature_write_service import _feature_id_to_rowid

logger = logging.getLogger(__name__)

# Lifted from feature_write_service so bbox upkeep cannot drift between the two
# writers. Every ? is the same GeoJSON string.
BBOX_STRUCT_SQL = (
    "struct_pack("
    "xmin := ST_XMin(ST_MakeValid(ST_GeomFromGeoJSON(?))), "
    "ymin := ST_YMin(ST_MakeValid(ST_GeomFromGeoJSON(?))), "
    "xmax := ST_XMax(ST_MakeValid(ST_GeomFromGeoJSON(?))), "
    "ymax := ST_YMax(ST_MakeValid(ST_GeomFromGeoJSON(?))))"
)

TO_3857 = "ST_Transform({geom}, 'EPSG:4326', 'EPSG:3857', always_xy := true)"


def mint_id() -> str:
    """An id for a node or edge the editor created.

    Prefixed so edited geometry stays distinguishable from imported GERS ids.
    The artifact renumbers with row_number(), so the value only has to be
    unique within the layer.
    """
    return f"edit:{uuid.uuid4()}"


def resolve_feature_ids(
    con: Any, table: str, feature_ids: Sequence[str]
) -> dict[str, str]:
    """Map the editor's feature ids onto the layer's own ``id`` values.

    Feature ids come from the rendered tiles and are ``rowid + 1``; everything
    downstream keys on the layer's ``id`` column instead, because a delete
    renumbers the rowids of the rows that survive it.

    Only ids that resolve are returned. A caller must treat a missing one as an
    error rather than writing to whatever the raw value happens to match.
    """
    numeric = [fid for fid in feature_ids if str(fid).isdigit()]
    if not numeric:
        return {}
    rowids = [_feature_id_to_rowid(fid) for fid in numeric]
    placeholders = ", ".join(["?"] * len(rowids))
    rows = con.execute(
        f'SELECT rowid, "id" FROM {table} WHERE rowid IN ({placeholders})',
        rowids,
    ).fetchall()
    by_rowid = {int(r[0]): r[1] for r in rows}
    resolved: dict[str, str] = {}
    for fid, rowid in zip(numeric, rowids):
        if rowid in by_rowid:
            resolved[str(fid)] = by_rowid[rowid]
    return resolved


def fetch_candidates(
    con: Any,
    edges_table: str,
    nodes_table: str,
    bbox_3857: tuple[float, float, float, float],
    exclude_edge_ids: Iterable[str],
) -> tuple[list[NodeCandidate], list[EdgeCandidate]]:
    """Nodes and edges near the edit, in projected metres.

    Restricted to the edit's own bounding box grown by the tolerance: snapping
    only ever looks at what the user drew next to, and a city-wide network is
    far too large to load whole.
    """
    xmin, ymin, xmax, ymax = bbox_3857
    box = f"ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax})"
    node_rows = con.execute(
        f"""
        WITH projected AS (
            SELECT "id", {TO_3857.format(geom="geometry")} AS g FROM {nodes_table}
        )
        SELECT "id", ST_X(g), ST_Y(g) FROM projected
        WHERE ST_Intersects(g, {box})
        """
    ).fetchall()
    nodes = [
        NodeCandidate(node_id=r[0], x=float(r[1]), y=float(r[2])) for r in node_rows
    ]

    excluded = set(exclude_edge_ids)
    edge_rows = con.execute(
        f"""
        WITH projected AS (
            SELECT "id", source_node, target_node,
                   {TO_3857.format(geom="geometry")} AS g
            FROM {edges_table}
        )
        SELECT "id", source_node, target_node, ST_AsText(g) FROM projected
        WHERE ST_Intersects(g, {box})
        """
    ).fetchall()
    edges = [
        EdgeCandidate(
            edge_id=r[0],
            source_node=r[1],
            target_node=r[2],
            geometry=wkt.loads(r[3]),
        )
        for r in edge_rows
        if r[0] not in excluded
    ]
    return nodes, edges


def _node_insert_sql(nodes_table: str, columns: Sequence[str], geom_expr: str) -> str:
    """INSERT for a node, writing only the columns the layer actually has.

    ``bbox`` is a struct whose xmin/ymin/xmax/ymax are subfields, not columns of
    their own — writing them as columns fails on the real layers.
    """
    target = ['"id"']
    select = ["?"]
    if "is_synthetic" in columns:
        target.append('"is_synthetic"')
        select.append("TRUE")
    target.append('"geometry"')
    select.append("g")
    if "bbox" in columns:
        target.append('"bbox"')
        select.append(
            "struct_pack(xmin := ST_XMin(g), ymin := ST_YMin(g), "
            "xmax := ST_XMax(g), ymax := ST_YMax(g))"
        )
    for axis, fn in (
        ("xmin", "ST_XMin"),
        ("ymin", "ST_YMin"),
        ("xmax", "ST_XMax"),
        ("ymax", "ST_YMax"),
    ):
        if axis in columns:
            target.append(f'"{axis}"')
            select.append(f"{fn}(g)")
    return (
        f"INSERT INTO {nodes_table} ({', '.join(target)}) "
        f"SELECT {', '.join(select)} FROM ({geom_expr})"
    )


def insert_node(
    con: Any,
    nodes_table: str,
    columns: Sequence[str],
    node_id: str,
    x_3857: float,
    y_3857: float,
) -> None:
    """Add a node at a projected coordinate, stored back as 4326."""
    geom_expr = (
        f"SELECT ST_Transform(ST_Point({x_3857}, {y_3857}), 'EPSG:3857', "
        "'EPSG:4326', always_xy := true) AS g"
    )
    con.execute(_node_insert_sql(nodes_table, columns, geom_expr), [node_id])


def insert_node_on_edge(
    con: Any,
    nodes_table: str,
    columns: Sequence[str],
    edges_table: str,
    node_id: str,
    edge_id: str,
    fraction: float,
) -> None:
    """Add a node at a fraction along an edge, exactly on its stored geometry."""
    geom_expr = (
        f"SELECT ST_LineInterpolatePoint(geometry, {float(fraction)}) AS g "
        f'FROM {edges_table} WHERE "id" = ?'
    )
    con.execute(
        _node_insert_sql(nodes_table, columns, geom_expr), [node_id, edge_id]
    )


def split_edge(
    con: Any,
    edges_table: str,
    columns: Sequence[str],
    edge_id: str,
    fraction: float,
    left_id: str,
    right_id: str,
    new_node_id: str,
) -> None:
    """Replace an edge with two halves meeting at a new node.

    Both halves inherit every attribute of the original. Nothing length-derived
    needs recomputing: the edges layer stores no length, the artifact build
    measures it.
    """
    for new_id, start, end, source, target in (
        (left_id, 0.0, fraction, None, new_node_id),
        (right_id, fraction, 1.0, new_node_id, None),
    ):
        half = f"ST_LineSubstring(geometry, {float(start)}, {float(end)})"
        replacements = [
            "? AS \"id\"",
            f"{half} AS geometry",
            "coalesce(?, source_node) AS source_node",
            "coalesce(?, target_node) AS target_node",
        ]
        if "bbox" in columns:
            replacements.append(
                f"struct_pack(xmin := ST_XMin({half}), ymin := ST_YMin({half}), "
                f"xmax := ST_XMax({half}), ymax := ST_YMax({half})) AS bbox"
            )
        for axis, fn in (
            ("xmin", "ST_XMin"),
            ("ymin", "ST_YMin"),
            ("xmax", "ST_XMax"),
            ("ymax", "ST_YMax"),
        ):
            if axis in columns:
                replacements.append(f"{fn}({half}) AS {axis}")
        con.execute(
            f"INSERT INTO {edges_table} BY NAME "
            f"SELECT * REPLACE ({', '.join(replacements)}) "
            f'FROM {edges_table} WHERE "id" = ?',
            [new_id, source, target, edge_id],
        )
    con.execute(f'DELETE FROM {edges_table} WHERE "id" = ?', [edge_id])


def insert_edge(
    con: Any,
    edges_table: str,
    column_names: Sequence[str],
    edge_id: str,
    geometry: dict[str, Any],
    properties: dict[str, Any],
    source_node: str,
    target_node: str,
) -> None:
    """Add an edge with its resolved endpoints."""
    geom_json = json.dumps(geometry)
    columns = ['"id"', '"geometry"', '"source_node"', '"target_node"']
    placeholders = ["?", "ST_MakeValid(ST_GeomFromGeoJSON(?))", "?", "?"]
    values: list[Any] = [edge_id, geom_json, source_node, target_node]

    for key, value in properties.items():
        if key in ("id", "geometry", "source_node", "target_node", "bbox"):
            continue
        if key not in column_names:
            continue
        columns.append(f'"{key}"')
        placeholders.append("?")
        values.append(value)

    if "bbox" in column_names:
        columns.append('"bbox"')
        placeholders.append(BBOX_STRUCT_SQL)
        values.extend([geom_json] * 4)
    for axis, fn in (
        ("xmin", "ST_XMin"),
        ("ymin", "ST_YMin"),
        ("xmax", "ST_XMax"),
        ("ymax", "ST_YMax"),
    ):
        if axis in column_names:
            columns.append(f'"{axis}"')
            placeholders.append(f"{fn}(ST_MakeValid(ST_GeomFromGeoJSON(?)))")
            values.append(geom_json)

    con.execute(
        f"INSERT INTO {edges_table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)})",
        values,
    )


def update_edge(
    con: Any,
    edges_table: str,
    column_names: Sequence[str],
    edge_id: str,
    geometry: dict[str, Any],
    properties: dict[str, Any],
    source_node: str,
    target_node: str,
) -> None:
    """Replace an edge's geometry, endpoints and attributes."""
    geom_json = json.dumps(geometry)
    assignments = [
        '"geometry" = ST_MakeValid(ST_GeomFromGeoJSON(?))',
        '"source_node" = ?',
        '"target_node" = ?',
    ]
    values: list[Any] = [geom_json, source_node, target_node]

    for key, value in properties.items():
        if key in ("id", "geometry", "source_node", "target_node", "bbox"):
            continue
        if key not in column_names:
            continue
        assignments.append(f'"{key}" = ?')
        values.append(value)

    if "bbox" in column_names:
        assignments.append(f'"bbox" = {BBOX_STRUCT_SQL}')
        values.extend([geom_json] * 4)
    for axis, fn in (
        ("xmin", "ST_XMin"),
        ("ymin", "ST_YMin"),
        ("xmax", "ST_XMax"),
        ("ymax", "ST_YMax"),
    ):
        if axis in column_names:
            assignments.append(f'"{axis}" = {fn}(ST_MakeValid(ST_GeomFromGeoJSON(?)))')
            values.append(geom_json)

    values.append(edge_id)
    con.execute(
        f"UPDATE {edges_table} SET {', '.join(assignments)} WHERE \"id\" = ?", values
    )
    changed = con.execute(
        f'SELECT count(*) FROM {edges_table} WHERE "id" = ?', [edge_id]
    ).fetchone()
    if not changed or changed[0] == 0:
        raise ValueError(
            f"Edge {edge_id} is no longer in the layer, so the edit could not be "
            "applied. Reload before saving."
        )


def delete_edges_by_id(con: Any, edges_table: str, edge_ids: Sequence[str]) -> None:
    """Remove edges by their own ids.

    Raises when an id is not there: a delete that quietly removes nothing looks
    identical to a successful one from the client's side.
    """
    if not edge_ids:
        return
    placeholders = ", ".join(["?"] * len(edge_ids))
    present = con.execute(
        f'SELECT count(*) FROM {edges_table} WHERE "id" IN ({placeholders})',
        list(edge_ids),
    ).fetchone()
    if not present or present[0] != len(set(edge_ids)):
        raise ValueError(
            "Some edges are no longer in the layer, so the deletion could not be "
            "applied. Reload before saving."
        )
    con.execute(
        f'DELETE FROM {edges_table} WHERE "id" IN ({placeholders})', list(edge_ids)
    )


def surviving_edge_endpoints(
    con: Any, edges_table: str, node_ids: Sequence[str]
) -> list[tuple[str, str]]:
    """Endpoint pairs of every edge still referencing any of these nodes."""
    if not node_ids:
        return []
    placeholders = ", ".join(["?"] * len(node_ids))
    rows = con.execute(
        f"""
        SELECT source_node, target_node FROM {edges_table}
        WHERE source_node IN ({placeholders}) OR target_node IN ({placeholders})
        """,
        list(node_ids) * 2,
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def delete_nodes_by_id(con: Any, nodes_table: str, node_ids: Iterable[str]) -> int:
    """Remove nodes by id. Returns how many were removed."""
    ids = list(node_ids)
    if not ids:
        return 0
    placeholders = ", ".join(["?"] * len(ids))
    con.execute(f'DELETE FROM {nodes_table} WHERE "id" IN ({placeholders})', ids)
    return len(ids)


def column_names(con: Any, table: str) -> list[str]:
    """Column names of a layer table.

    Read off an empty result rather than PRAGMA table_info, which does not take
    a catalog-qualified name like ``lake.schema.table``.
    """
    cursor = con.execute(f"SELECT * FROM {table} LIMIT 0")
    return [d[0] for d in cursor.description]
