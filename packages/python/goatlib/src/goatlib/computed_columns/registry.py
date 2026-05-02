"""Definitions of computed column kinds.

A `ComputedKind` is metadata + a SQL fragment template for one kind of
computed column. The registry maps kind name to its definition.

When `formula` (custom user expressions) is added later, it will be a
`ComputedKind` whose `compute_sql_template` is supplied dynamically per
column rather than being a constant.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputedKind:
    """Metadata for a computed column kind.

    Attributes:
        name: Public kind name (e.g. "area").
        duckdb_type: DuckDB column type (e.g. "DOUBLE").
        allowed_geom_types: Geometry types this kind is valid on.
        depends_on: Source columns whose change should trigger recompute.
        compute_sql_template: SQL with {geom} placeholder for the geometry
            column name (always quoted by `compute_sql`).
    """

    name: str
    duckdb_type: str
    allowed_geom_types: frozenset[str]
    depends_on: tuple[str, ...]
    compute_sql_template: str

    def compute_sql(self, geom_column: str = "geometry") -> str:
        """Return the SQL fragment that computes this column's value.

        The geometry column is always double-quoted.
        """
        return self.compute_sql_template.format(geom=f'"{geom_column}"')


# Built-in computed column kinds.
#
# IMPORTANT — DuckDB spatial axis-order quirk (verified on v1.4.4):
# DuckDB's ST_*_Spheroid family treats the geometry's first axis (X) as
# latitude and the second (Y) as longitude. Our data uses the standard
# (lon, lat) order via ST_GeomFromGeoJSON, so we must wrap with
# ST_FlipCoordinates before any *_Spheroid call. Without this, the
# function applies cos(longitude) instead of cos(latitude) and the
# result is inflated by ~1/cos(latitude) at non-equatorial latitudes
# (e.g. ~50 % too large for central Europe).
#
# Cross-checked against pyproj.Geod (Karney), EPSG:3035 LAEA, and UTM
# 32N planar — all three agree with the flipped form to ~0.1 %.
COMPUTED_KIND_REGISTRY: dict[str, ComputedKind] = {
    "area": ComputedKind(
        name="area",
        duckdb_type="DOUBLE",
        allowed_geom_types=frozenset({"polygon", "multipolygon"}),
        depends_on=("geometry",),
        compute_sql_template="ST_Area_Spheroid(ST_FlipCoordinates({geom}))",
    ),
    "perimeter": ComputedKind(
        name="perimeter",
        duckdb_type="DOUBLE",
        allowed_geom_types=frozenset({"polygon", "multipolygon"}),
        depends_on=("geometry",),
        compute_sql_template="ST_Perimeter_Spheroid(ST_FlipCoordinates({geom}))",
    ),
    "length": ComputedKind(
        name="length",
        duckdb_type="DOUBLE",
        allowed_geom_types=frozenset({"line", "multiline"}),
        depends_on=("geometry",),
        compute_sql_template="ST_Length_Spheroid(ST_FlipCoordinates({geom}))",
    ),
}


def get_computed_kind(name: str) -> ComputedKind | None:
    """Return the `ComputedKind` for `name`, or None if unknown."""
    return COMPUTED_KIND_REGISTRY.get(name)


def is_computed_kind(name: str) -> bool:
    """Return True iff `name` is a computed kind in the registry."""
    return name in COMPUTED_KIND_REGISTRY
