"""Write flattened records as typed GeoParquet member layers.

The schema is declared rather than inferred. Handing the runner GeoJSON instead
would let column types follow the data: a network with no ``level_rules`` yields
an all-null column, which infers as VARCHAR, while a network that has them yields
INTEGER — so two imports of the same bundle type would disagree on their layer
schema, and anything reading the layer (the routing artifact, CQL2 filters) would
have to cope with both.

Geometry goes through DuckDB so the output carries GeoParquet metadata — the
runner's ingest detects the geometry column by DuckDB type, and a plain WKB blob
would not be recognised. Writing via ``write_optimized_parquet`` also picks up the
bbox struct, Hilbert ordering and Parquet V2 that every other layer gets.
"""

import logging
from typing import Any, Dict, List, Sequence

import duckdb
import pyarrow as pa
from shapely.geometry import LineString, Point

from goatlib.io.parquet import write_optimized_parquet

logger = logging.getLogger(__name__)

# WKB on the way in; DuckDB turns it into a real geometry column on write.
_GEOMETRY = ("geometry", pa.binary())

EDGE_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("original_id", pa.string()),
        ("class", pa.string()),
        ("subclass", pa.string()),
        ("name", pa.string()),
        ("source_node", pa.string()),
        ("target_node", pa.string()),
        ("surface", pa.string()),
        ("speed_limit_kph_forward", pa.int32()),
        ("speed_limit_kph_backward", pa.int32()),
        ("other", pa.string()),
        _GEOMETRY,
    ]
)

NODE_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("is_synthetic", pa.bool_()),
        _GEOMETRY,
    ]
)


def write_edges(records: Sequence[Dict[str, Any]], path: str) -> str:
    """Write edge records, converting ``coordinates`` to LineString geometry."""
    return _write(records, path, EDGE_SCHEMA, "coordinates", _line_wkb)


def write_nodes(records: Sequence[Dict[str, Any]], path: str) -> str:
    """Write node records, converting ``coordinate`` to Point geometry."""
    return _write(records, path, NODE_SCHEMA, "coordinate", _point_wkb)


def _write(
    records: Sequence[Dict[str, Any]],
    path: str,
    schema: pa.Schema,
    geometry_key: str,
    to_wkb: Any,
) -> str:
    rows: List[Dict[str, Any]] = []
    for record in records:
        geometry = record.get(geometry_key)
        if geometry is None:
            continue
        row = {name: record.get(name) for name in schema.names if name != "geometry"}
        row["geometry"] = to_wkb(geometry)
        rows.append(row)

    table = pa.Table.from_pylist(rows, schema=schema)
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial")
        con.register("records", table)
        # Same optimiser every other layer goes through — bbox struct for
        # row-group pruning, Hilbert ordering, Parquet V2 — so a bundle's layers
        # aren't second-class for tile and feature queries. REPLACE keeps the
        # declared column order and types; only geometry changes type.
        write_optimized_parquet(
            con,
            "SELECT * REPLACE (ST_GeomFromWKB(geometry) AS geometry) FROM records",
            path,
            geometry_column="geometry",
        )
    finally:
        con.close()
    logger.debug("Wrote %d row(s) to %s", len(rows), path)
    return path


def _line_wkb(coordinates: Sequence[Any]) -> bytes:
    return bytes(LineString([tuple(c) for c in coordinates]).wkb)


def _point_wkb(coordinate: Sequence[float]) -> bytes:
    return bytes(Point(tuple(coordinate)).wkb)
