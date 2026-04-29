"""Travel Cost Matrix tool for Windmill.

Computes many-to-many travel costs between origin and destination point layers
via the local C++ routing backend. Produces two outputs:
1. Matrix table (non-geom): origin_id, destination_id, cost
2. Destination points (geom): destination geometry with min_cost from any origin
"""

import asyncio
import logging
import math
import tempfile
import uuid as uuid_module
from pathlib import Path
from typing import Any, Self

import duckdb
from pydantic import Field

from goatlib.analysis.accessibility import TravelCostMatrixTool
from goatlib.analysis.schemas.travel_cost_matrix import (
    AccessEgressMode,
    CostType,
    PTMode,
    PTTimeWindow,
    RoutingMode,
    TravelCostMatrixParams,
    Weekday,
)
from goatlib.analysis.schemas.ui import (
    SECTION_ROUTING,
    UISection,
    ui_field,
    ui_sections,
)
from goatlib.models.io import DatasetMetadata
from goatlib.tools.base import BaseToolRunner
from goatlib.tools.catchment_area_v2 import (
    ACCESS_EGRESS_MODE_LABELS,
    COST_TYPE_ICONS,
    COST_TYPE_LABELS,
    PT_MODE_LABELS,
    ROUTING_MODE_ICONS as _CATCHMENT_ROUTING_MODE_ICONS,
    ROUTING_MODE_LABELS as _CATCHMENT_ROUTING_MODE_LABELS,
)
from goatlib.tools.schemas import ToolInputBase, ToolOutputBase

logger = logging.getLogger(__name__)

# Extend routing mode icons/labels with matrix-only modes
ROUTING_MODE_ICONS = {
    **_CATCHMENT_ROUTING_MODE_ICONS,
    "flight_distance": "plane",
}
ROUTING_MODE_LABELS = {
    **_CATCHMENT_ROUTING_MODE_LABELS,
    "flight_distance": "routing_modes.flight_distance",
}

# =========================================================================
# UI Sections
# =========================================================================

SECTION_INPUT = UISection(
    id="input",
    order=5,
    icon="layers",
    label="Input",
    label_de="Eingabe",
    depends_on={"routing_mode": {"$ne": None}},
)

SECTION_CONFIGURATION = UISection(
    id="configuration",
    order=3,
    icon="settings",
    label_key="configuration",
    depends_on={"routing_mode": {"$in": ["walking", "bicycle", "pedelec", "car", "pt"]}},
)

SECTION_RESULT = UISection(
    id="result",
    order=7,
    icon="save",
    label="Result layer",
    label_de="Ergebnis-Layer",
    depends_on={"routing_mode": {"$ne": None}},
)


# =========================================================================
# Windmill Params
# =========================================================================


class TravelCostMatrixWindmillParams(ToolInputBase):
    """Compute travel times and distances between origin and destination point layers.

    This schema extends ToolInputBase with travel cost matrix specific parameters.
    The frontend renders this dynamically based on x-ui metadata.
    """

    model_config = {
        "json_schema_extra": ui_sections(
            SECTION_INPUT,
            SECTION_ROUTING,
            SECTION_CONFIGURATION,
            SECTION_RESULT,
        )
    }

    # Hide the generic result_layer_name from ToolInputBase
    result_layer_name: str | None = Field(
        default=None,
        json_schema_extra=ui_field(section="result", hidden=True),
    )

    # =========================================================================
    # Result Section
    # =========================================================================

    destinations_layer_name: str | None = Field(
        default="Destinations",
        description="Name for the destination points result layer.",
        json_schema_extra=ui_field(
            section="result",
            field_order=1,
            label="Destinations layer name",
            label_de="Name des Zielpunkte-Layers",
            widget_options={
                "default_en": "Destinations",
                "default_de": "Zielpunkte",
            },
        ),
    )

    matrix_layer_name: str | None = Field(
        default="Travel Cost Matrix",
        description="Name for the cost matrix table layer.",
        json_schema_extra=ui_field(
            section="result",
            field_order=2,
            label="Matrix layer name",
            label_de="Name des Matrix-Layers",
            widget_options={
                "default_en": "Travel Cost Matrix",
                "default_de": "Reisezeitmatrix",
            },
        ),
    )

    # =========================================================================
    # Input Section
    # =========================================================================

    origin_layer_id: str = Field(
        ...,
        description="Layer containing origin points.",
        json_schema_extra=ui_field(
            section="input",
            field_order=1,
            label="Origins layer",
            label_de="Startpunkte-Layer",
            group_label="Origins",
            widget="layer-selector",
            widget_options={"geometry_types": ["Point", "MultiPoint"]},
        ),
    )

    origin_layer_filter: dict[str, Any] | None = Field(
        None,
        description="CQL2-JSON filter for origin layer.",
        json_schema_extra=ui_field(section="input", field_order=2, hidden=True),
    )

    destination_layer_id: str = Field(
        ...,
        description="Layer containing destination points.",
        json_schema_extra=ui_field(
            section="input",
            field_order=4,
            label="Destinations layer",
            label_de="Zielpunkte-Layer",
            group_label="Destinations",
            widget="layer-selector",
            widget_options={"geometry_types": ["Point", "MultiPoint"]},
        ),
    )

    destination_layer_filter: dict[str, Any] | None = Field(
        None,
        description="CQL2-JSON filter for destination layer.",
        json_schema_extra=ui_field(section="input", field_order=4, hidden=True),
    )

    origin_id_column: str = Field(
        ...,
        description="Column used to label origins in the result matrix.",
        json_schema_extra=ui_field(
            section="input",
            field_order=3,
            label="Origins label",
            label_de="Herkunft-Bezeichnung",
            widget="field-selector",
            widget_options={"source_layer": "origin_layer_id"},
        ),
    )

    destination_id_column: str = Field(
        ...,
        description="Column used to label destinations in the result matrix.",
        json_schema_extra=ui_field(
            section="input",
            field_order=5,
            label="Destinations label",
            label_de="Ziel-Bezeichnung",
            widget="field-selector",
            widget_options={"source_layer": "destination_layer_id"},
        ),
    )

    # =========================================================================
    # Routing Section
    # =========================================================================

    routing_mode: RoutingMode = Field(
        ...,
        description="Transport mode for routing.",
        json_schema_extra=ui_field(
            section="routing",
            field_order=1,
            label_key="routing_mode",
            enum_icons=ROUTING_MODE_ICONS,
            enum_labels=ROUTING_MODE_LABELS,
        ),
    )

    pt_modes: list[PTMode] | None = Field(
        default=list(PTMode),
        description="Public transport modes to include.",
        json_schema_extra=ui_field(
            section="routing",
            field_order=2,
            label_key="choose_pt_mode",
            enum_labels=PT_MODE_LABELS,
            visible_when={"routing_mode": "pt"},
        ),
    )

    # =========================================================================
    # Configuration Section
    # =========================================================================

    cost_type: CostType = Field(
        default=CostType.time,
        description="Measure travel cost by time or distance.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=1,
            label="Calculate by",
            label_de="Berechnung nach",
            enum_labels=COST_TYPE_LABELS,
            enum_icons=COST_TYPE_ICONS,
            visible_when={
                "routing_mode": {"$in": ["walking", "bicycle", "pedelec", "car"]}
            },
        ),
    )

    # PT time window (always visible for PT, not behind advanced)
    pt_day: Weekday = Field(
        default=Weekday.weekday,
        description="Day type for PT schedule.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=2,
            label_key="weekday",
            visible_when={"routing_mode": "pt"},
        ),
    )

    pt_start_time: int = Field(
        default=25200,
        description="PT window start (seconds from midnight).",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=3,
            label_key="from_time",
            widget="time-picker",
            inline_group="pt_time_window",
            inline_flex="1 0 0",
            visible_when={"routing_mode": "pt"},
        ),
    )

    pt_end_time: int = Field(
        default=32400,
        description="PT window end (seconds from midnight).",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=4,
            label_key="to_time",
            widget="time-picker",
            inline_group="pt_time_window",
            inline_flex="1 0 0",
            visible_when={"routing_mode": "pt"},
        ),
    )

    # =========================================================================
    # Advanced Options
    # =========================================================================

    show_advanced: bool = Field(
        default=False,
        description="Show advanced configuration options.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=10,
            label_key="advanced_options",
        ),
    )

    # Cost limits (advanced)
    max_cost_time_active: int = Field(
        default=15,
        description="Maximum travel time in minutes.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=11,
            label="Limit - Time (min)",
            label_de="Limit - Zeit (Min)",
            inline_group="cost_limit",
            inline_flex="1 0 0",
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "Active mobility travel time must be between 1 and 45 minutes",
                    "max": 45,
                    "min": 1,
                },
            },
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": {"$in": ["walking", "bicycle", "pedelec"]}},
                    {"cost_type": "time"},
                ]
            },
        ),
    )

    max_cost_time_car: int = Field(
        default=30,
        description="Maximum travel time in minutes.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=11,
            label="Limit - Time (min)",
            label_de="Limit - Zeit (Min)",
            inline_group="cost_limit",
            inline_flex="1 0 0",
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "Car travel time must be between 1 and 90 minutes",
                    "max": 90,
                    "min": 1,
                },
            },
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "car"},
                    {"cost_type": "time"},
                ]
            },
        ),
    )

    max_cost_time_pt: int = Field(
        default=30,
        description="Maximum travel time in minutes.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=5,
            label="Travel time limit (min)",
            label_de="Reisezeitlimit (Min)",
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "PT travel time must be between 1 and 90 minutes",
                    "max": 90,
                    "min": 1,
                },
            },
            visible_when={"routing_mode": "pt"},
        ),
    )

    max_cost_distance: int = Field(
        default=500,
        description="Maximum distance in meters.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=11,
            label="Limit - Distance (m)",
            label_de="Limit - Distanz (m)",
            inline_group="cost_limit",
            inline_flex="1 0 0",
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "Distance must be between 50 and 20,000 meters",
                    "max": 20000,
                    "min": 50,
                },
            },
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": {"$in": ["walking", "bicycle", "pedelec"]}},
                    {"cost_type": "distance"},
                ]
            },
        ),
    )

    max_cost_distance_car: int = Field(
        default=5000,
        description="Maximum distance in meters.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=11,
            label="Limit - Distance (m)",
            label_de="Limit - Distanz (m)",
            inline_group="cost_limit",
            inline_flex="1 0 0",
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "Distance must be between 50 and 100,000 meters",
                    "max": 100000,
                    "min": 50,
                },
            },
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "car"},
                    {"cost_type": "distance"},
                ]
            },
        ),
    )

    speed: float = Field(
        default=5,
        description="Travel speed in km/h.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=5,
            label_key="speed",
            visible_when={
                "$and": [
                    {"routing_mode": {"$in": ["walking", "bicycle", "pedelec"]}},
                    {"cost_type": "time"},
                ]
            },
            widget_options={
                "default_by_field": {
                    "field": "routing_mode",
                    "values": {
                        "walking": 5,
                        "bicycle": 15,
                        "pedelec": 23,
                    },
                }
            },
        ),
    )

    pt_max_transfers: int = Field(
        default=5,
        description="Maximum number of transit transfers.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=13,
            label="Max. transfers",
            label_de="Max. Umstiege",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                ]
            },
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "Max transfers must be between 0 and 10",
                    "max": 10,
                    "min": 0,
                },
            },
        ),
    )

    pt_access_mode: AccessEgressMode = Field(
        default=AccessEgressMode.walk,
        description="Mode to reach transit stops.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=20,
            label_key="access_mode",
            group_label="Access leg",
            enum_labels=ACCESS_EGRESS_MODE_LABELS,
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                ]
            },
        ),
    )

    pt_access_cost_type: CostType = Field(
        default=CostType.time,
        description="Access leg cost type.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=21,
            label_key="measure_type",
            enum_labels=COST_TYPE_LABELS,
            enum_icons=COST_TYPE_ICONS,
            inline_group="pt_access_cost",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                ]
            },
        ),
    )

    pt_access_max_cost_time: int = Field(
        default=15,
        description="Access leg budget in minutes.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=22,
            label_key="limit",
            inline_group="pt_access_cost",
            inline_flex="1 0 0",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_access_cost_type": "time"},
                ]
            },
            widget_options={
                "max_value_from": {
                    "fields": [
                        {"field": "max_cost_time_pt"},
                    ],
                    "message": "access_budget_exceeds_limit",
                    "min": 1,
                },
            },
        ),
    )

    pt_access_max_cost_distance: int = Field(
        default=500,
        description="Access leg budget in meters.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=22,
            label_key="limit",
            inline_group="pt_access_cost",
            inline_flex="1 0 0",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_access_cost_type": "distance"},
                ]
            },
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "access_budget_exceeds_limit",
                    "min": 50,
                    "max": 20000,
                },
            },
        ),
    )

    pt_access_speed: float = Field(
        default=0.0,
        description="Access leg speed in km/h (0 = use default speed).",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=23,
            label="Speed (km/h)",
            label_de="Geschw. (km/h)",
            widget_options={"placeholder": "Default"},
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_access_cost_type": "time"},
                ]
            },
        ),
    )

    pt_egress_mode: AccessEgressMode = Field(
        default=AccessEgressMode.walk,
        description="Mode from transit stops to destination.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=24,
            label_key="pt_egress_mode",
            group_label="Egress leg",
            enum_labels=ACCESS_EGRESS_MODE_LABELS,
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                ]
            },
        ),
    )

    pt_egress_cost_type: CostType = Field(
        default=CostType.time,
        description="Egress leg cost type.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=25,
            label_key="measure_type",
            enum_labels=COST_TYPE_LABELS,
            enum_icons=COST_TYPE_ICONS,
            inline_group="pt_egress_cost",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                ]
            },
        ),
    )

    pt_egress_max_cost_time: int = Field(
        default=15,
        description="Egress leg budget in minutes.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=26,
            label_key="limit",
            inline_group="pt_egress_cost",
            inline_flex="1 0 0",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_egress_cost_type": "time"},
                ]
            },
            widget_options={
                "max_value_from": {
                    "fields": [
                        {"field": "max_cost_time_pt"},
                    ],
                    "message": "egress_budget_exceeds_limit",
                    "min": 1,
                },
            },
        ),
    )

    pt_egress_max_cost_distance: int = Field(
        default=500,
        description="Egress leg budget in meters.",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=26,
            label_key="limit",
            inline_group="pt_egress_cost",
            inline_flex="1 0 0",
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_egress_cost_type": "distance"},
                ]
            },
            widget_options={
                "max_value_from": {
                    "fields": [],
                    "message": "egress_budget_exceeds_limit",
                    "min": 50,
                    "max": 20000,
                },
            },
        ),
    )

    pt_egress_speed: float = Field(
        default=0.0,
        description="Egress leg speed in km/h (0 = use default speed).",
        json_schema_extra=ui_field(
            section="configuration",
            field_order=27,
            label="Speed (km/h)",
            label_de="Geschw. (km/h)",
            widget_options={"placeholder": "Default"},
            visible_when={
                "$and": [
                    {"show_advanced": True},
                    {"routing_mode": "pt"},
                    {"pt_egress_cost_type": "time"},
                ]
            },
        ),
    )

    def resolve_max_cost(self: Self, extent_m: float = 0.0) -> float:
        """Resolve the effective max_cost from mode-specific UI fields.

        When advanced options are not shown, derives the budget from the
        actual O-D extent and mode speed so the network is just large
        enough. The user only gets NULL results when they explicitly
        set a limit via advanced options.
        """
        # PT always uses the explicit limit field (always visible)
        if self.routing_mode == RoutingMode.pt:
            return float(self.max_cost_time_pt)

        if not self.show_advanced:
            # Derive from extent: distance / speed → time, with detour margin
            detour_distance = extent_m * 1.4
            if self.cost_type == CostType.distance:
                return detour_distance
            # Use user-configured speed if set, otherwise mode default
            default_speeds = {
                RoutingMode.walking: 5.0,
                RoutingMode.bicycle: 15.0,
                RoutingMode.pedelec: 23.0,
                RoutingMode.car: 50.0,
            }
            speed_km_h = (
                self.speed if self.speed > 0
                else default_speeds.get(self.routing_mode, 5.0)
            )
            return detour_distance / (speed_km_h * 1000.0 / 60.0)

        if self.cost_type == CostType.distance:
            if self.routing_mode == RoutingMode.car:
                return float(self.max_cost_distance_car)
            return float(self.max_cost_distance)
        if self.routing_mode == RoutingMode.pt:
            return float(self.max_cost_time_pt)
        if self.routing_mode == RoutingMode.car:
            return float(self.max_cost_time_car)
        return float(self.max_cost_time_active)


# =========================================================================
# Tool Runner
# =========================================================================


class TravelCostMatrixToolRunner(BaseToolRunner[TravelCostMatrixWindmillParams]):
    """Travel Cost Matrix tool runner for Windmill.

    Creates two output layers:
    1. Matrix table (non-geom): origin_id, destination_id, cost
    2. Destination points (geom): destination geometry annotated with min_cost
    """

    tool_class = TravelCostMatrixTool
    output_geometry_type = "Point"
    default_output_name = "Travel Cost Matrix"
    default_destinations_name = "Destinations"

    @classmethod
    def predict_output_schema(
        cls,
        input_schemas: dict[str, dict[str, str]],
        params: dict[str, Any],
    ) -> dict[str, str]:
        return {
            "origin": "VARCHAR",
            "destination": "VARCHAR",
            "travel_cost": "INTEGER",
        }

    @staticmethod
    def _extract_coordinates_from_parquet(
        parquet_path: Path,
        id_column: str,
    ) -> tuple[list[float], list[float], list[str]]:
        """Extract lat/lon coordinates and IDs from a GeoParquet point layer."""
        con = duckdb.connect()
        try:
            con.execute("INSTALL spatial; LOAD spatial;")

            # Detect geometry column from parquet schema
            cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')").fetchall()
            geom_col = next(
                (c[0] for c in cols if "GEOMETRY" in c[1].upper() or c[0] in ("geom", "geometry")),
                None,
            )
            if not geom_col:
                raise RuntimeError(f"No geometry column found in {parquet_path}")

            id_select = f'CAST("{id_column}" AS VARCHAR)'

            result = con.execute(f"""
                SELECT
                    ST_Y("{geom_col}") as lat,
                    ST_X("{geom_col}") as lon,
                    {id_select} as id
                FROM read_parquet('{parquet_path}')
                WHERE "{geom_col}" IS NOT NULL
            """).fetchall()

            latitudes = [r[0] for r in result]
            longitudes = [r[1] for r in result]
            ids = [r[2] for r in result]
            return latitudes, longitudes, ids
        finally:
            con.close()

    @staticmethod
    def _compute_flight_distance_matrix(
        origin_lats: list[float], origin_lons: list[float], origin_ids: list[str],
        dest_lats: list[float], dest_lons: list[float], dest_ids: list[str],
        output_path: Path,
    ) -> None:
        """Compute geodesic distances (WGS84 ellipsoid) between all O-D pairs."""
        con = duckdb.connect()
        try:
            con.execute("INSTALL spatial; LOAD spatial;")

            # Build origin/destination value lists
            o_values = ",".join(
                f"('{o_id}', {lat}, {lon})"
                for o_id, lat, lon in zip(origin_ids, origin_lats, origin_lons)
            )
            d_values = ",".join(
                f"('{d_id}', {lat}, {lon})"
                for d_id, lat, lon in zip(dest_ids, dest_lats, dest_lons)
            )

            con.execute(f"""
                COPY (
                    SELECT
                        o.id AS origin,
                        d.id AS destination,
                        CAST(ROUND(ST_Distance_Spheroid(
                            ST_Point(o.lon, o.lat),
                            ST_Point(d.lon, d.lat)
                        )) AS INTEGER) AS travel_cost
                    FROM (VALUES {o_values}) AS o(id, lat, lon)
                    CROSS JOIN (VALUES {d_values}) AS d(id, lat, lon)
                ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
        finally:
            con.close()

    def _build_destination_points_parquet(
        self: Self,
        matrix_path: Path,
        dest_layer_parquet: Path,
        output_path: Path,
    ) -> None:
        """Join min travel cost onto the original destination layer."""
        con = duckdb.connect()
        try:
            con.execute("INSTALL spatial; LOAD spatial;")

            # Join by positional index — each destination row gets the average
            # cost across all origins for that specific point, regardless of
            # whether label values are unique.
            n_dests = con.execute(
                f"SELECT count(*) FROM read_parquet('{dest_layer_parquet}')"
            ).fetchone()[0]
            con.execute(f"""
                COPY (
                    SELECT
                        d.* EXCLUDE (_row_idx),
                        CAST(ROUND(m.avg_cost) AS INTEGER) as travel_cost
                    FROM (
                        SELECT *, (ROW_NUMBER() OVER () - 1) AS _row_idx
                        FROM read_parquet('{dest_layer_parquet}')
                    ) d
                    LEFT JOIN (
                        SELECT
                            dest_idx,
                            AVG(travel_cost) as avg_cost
                        FROM (
                            SELECT travel_cost,
                                   (ROW_NUMBER() OVER () - 1) % {n_dests} AS dest_idx
                            FROM read_parquet('{matrix_path}')
                        )
                        WHERE travel_cost IS NOT NULL
                        GROUP BY dest_idx
                    ) m ON d._row_idx = m.dest_idx
                    ORDER BY d._row_idx
                ) TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
        finally:
            con.close()

    def process(
        self: Self,
        params: TravelCostMatrixWindmillParams,
        temp_dir: Path,
    ) -> tuple[Path, DatasetMetadata]:
        """Run travel cost matrix analysis."""
        matrix_output_path = temp_dir / "matrix.parquet"
        destinations_output_path = temp_dir / "destinations.parquet"

        # Export layers to parquet
        origin_parquet = self.export_layer_to_parquet(
            layer_id=params.origin_layer_id,
            user_id=params.user_id,
            cql_filter=params.origin_layer_filter,
            scenario_id=params.scenario_id,
            project_id=params.project_id,
        )
        dest_parquet = self.export_layer_to_parquet(
            layer_id=params.destination_layer_id,
            user_id=params.user_id,
            cql_filter=params.destination_layer_filter,
            scenario_id=params.scenario_id,
            project_id=params.project_id,
        )

        # Extract coordinates and IDs from exported parquets
        origin_lats, origin_lons, origin_ids = self._extract_coordinates_from_parquet(
            origin_parquet, id_column=params.origin_id_column)
        dest_lats, dest_lons, dest_ids = self._extract_coordinates_from_parquet(
            dest_parquet, id_column=params.destination_id_column)

        # Validate matrix size
        n_combos = len(origin_lats) * len(dest_lats)
        if n_combos > 10_000:
            raise ValueError(
                f"Matrix size ({len(origin_lats)} origins × {len(dest_lats)} destinations "
                f"= {n_combos:,} pairs) exceeds the maximum of 10,000. "
                f"Reduce the number of origins or destinations."
            )

        # Compute max possible O-D distance using bbox corners.
        # The farthest O-D pair is bounded by the distance between the
        # farthest corners of the origin and destination bounding boxes.
        R = 6371000.0
        o_min_lat, o_max_lat = min(origin_lats), max(origin_lats)
        o_min_lon, o_max_lon = min(origin_lons), max(origin_lons)
        d_min_lat, d_max_lat = min(dest_lats), max(dest_lats)
        d_min_lon, d_max_lon = min(dest_lons), max(dest_lons)

        # Max lat/lon span between the two bbox extremes
        lat_span = max(abs(o_max_lat - d_min_lat), abs(d_max_lat - o_min_lat))
        lon_span = max(abs(o_max_lon - d_min_lon), abs(d_max_lon - o_min_lon))
        avg_lat = math.radians(
            (o_min_lat + o_max_lat + d_min_lat + d_max_lat) / 4.0)
        dy = math.radians(lat_span) * R
        dx = math.radians(lon_span) * R * math.cos(avg_lat)
        extent_m = math.sqrt(dx * dx + dy * dy)

        # Validate max extent for routed modes.
        if params.routing_mode != RoutingMode.flight_distance:
            max_reach_m = {
                RoutingMode.walking: 50_000,
                RoutingMode.bicycle: 50_000,
                RoutingMode.pedelec: 50_000,
                RoutingMode.car: 300_000,
                RoutingMode.pt: 300_000,
            }.get(params.routing_mode, 300_000)

            if extent_m > max_reach_m:
                raise ValueError(
                    f"Origin-destination extent ({extent_m / 1000:.0f} km) exceeds "
                    f"the maximum reachable distance for {params.routing_mode.value} "
                    f"({max_reach_m / 1000:.0f} km). "
                    f"Reduce the area or choose a different mode."
                )

        if params.routing_mode == RoutingMode.flight_distance:
            # Geodesic distance — no routing needed.
            self._compute_flight_distance_matrix(
                origin_lats, origin_lons, origin_ids,
                dest_lats, dest_lons, dest_ids,
                matrix_output_path,
            )
        else:
            max_cost = params.resolve_max_cost(extent_m=extent_m)

            # Build PT time window if applicable
            time_window = None
            if params.routing_mode == RoutingMode.pt:
                time_window = PTTimeWindow(
                    weekday=params.pt_day,
                    from_time=params.pt_start_time,
                    to_time=params.pt_end_time,
                )

            analysis_params = TravelCostMatrixParams(
                origin_latitude=origin_lats,
                origin_longitude=origin_lons,
                origin_id=origin_ids,
                destination_latitude=dest_lats,
                destination_longitude=dest_lons,
                destination_id=dest_ids,
                routing_mode=params.routing_mode,
                cost_type=params.cost_type,
                max_cost=max_cost,
                speed=params.speed,
                # PT
                transit_modes=params.pt_modes,
                time_window=time_window,
                max_transfers=params.pt_max_transfers,
                access_mode=params.pt_access_mode,
                egress_mode=params.pt_egress_mode,
                access_cost_type=params.pt_access_cost_type,
                egress_cost_type=params.pt_egress_cost_type,
                access_max_cost=(
                    params.pt_access_max_cost_distance
                    if params.pt_access_cost_type == CostType.distance
                    else params.pt_access_max_cost_time
                ),
                egress_max_cost=(
                    params.pt_egress_max_cost_distance
                    if params.pt_egress_cost_type == CostType.distance
                    else params.pt_egress_max_cost_time
                ),
                access_speed=params.pt_access_speed,
                egress_speed=params.pt_egress_speed,
                output_path=str(matrix_output_path),
            )

            tool = self.tool_class()
            try:
                tool.run(analysis_params)
            finally:
                tool.cleanup()

        # Build destination points with min cost joined from original layer
        self._build_destination_points_parquet(
            matrix_output_path, dest_parquet,
            destinations_output_path
        )

        # Store for dual-output handling in run()
        self._matrix_path = matrix_output_path
        self._destinations_path = destinations_output_path

        # Return matrix as primary output
        matrix_metadata = DatasetMetadata(
            path=str(matrix_output_path),
            source_type="tabular",
            format="parquet",
        )
        return matrix_output_path, matrix_metadata

    def run(self: Self, params: TravelCostMatrixWindmillParams) -> dict[str, Any]:
        """Run analysis and create both matrix table and destination points layers."""
        temp_mode = getattr(params, "temp_mode", False)

        output_layer_id_matrix = str(uuid_module.uuid4())
        output_layer_id_dests = str(uuid_module.uuid4())

        output_name_matrix = (
            params.matrix_layer_name
            or params.result_layer_name
            or params.output_name
            or self.default_output_name
        )
        output_name_dests = (
            params.destinations_layer_name or self.default_destinations_name
        )

        logger.info(
            f"Starting tool: {self.__class__.__name__} "
            f"(user={params.user_id}, matrix={output_layer_id_matrix}, "
            f"dests={output_layer_id_dests}, temp_mode={temp_mode})"
        )

        asyncio.get_event_loop().run_until_complete(self._init_db_service())

        with tempfile.TemporaryDirectory(
            prefix=f"{self.__class__.__name__.lower()}_"
        ) as temp_dir:
            temp_path = Path(temp_dir)

            # Step 1: Run analysis
            matrix_parquet, matrix_metadata = self.process(params, temp_path)
            dests_parquet = self._destinations_path

            # Temp mode: return matrix only
            if temp_mode:
                result = self._write_temp_result(
                    params=params,
                    output_parquet=matrix_parquet,
                    output_name=output_name_matrix,
                    output_layer_id=output_layer_id_matrix,
                )
                asyncio.get_event_loop().run_until_complete(self._close_db_service())
                return result

            # Step 2: Ingest matrix table to DuckLake
            table_info_matrix = self._ingest_to_ducklake(
                user_id=params.user_id,
                layer_id=output_layer_id_matrix,
                parquet_path=matrix_parquet,
            )
            logger.info(f"Matrix table: {table_info_matrix['table_name']}")

            # Step 3: Ingest destination points to DuckLake
            table_info_dests = self._ingest_to_ducklake(
                user_id=params.user_id,
                layer_id=output_layer_id_dests,
                parquet_path=dests_parquet,
            )
            logger.info(f"Destinations table: {table_info_dests['table_name']}")

            # Refresh database pool — connections may have gone stale during analysis
            asyncio.get_event_loop().run_until_complete(self._close_db_service())

            # Step 4: Create matrix layer record (table type)
            result_info_matrix = asyncio.get_event_loop().run_until_complete(
                self._create_db_records(
                    output_layer_id=output_layer_id_matrix,
                    params=params,
                    output_name=output_name_matrix,
                    metadata=matrix_metadata,
                    table_info=table_info_matrix,
                )
            )

            # Step 5: Create destination points layer record
            dests_metadata = DatasetMetadata(
                path=str(dests_parquet),
                source_type="vector",
                format="geoparquet",
                geometry_type="Point",
                geometry_column="geometry",
            )
            result_info_dests = asyncio.get_event_loop().run_until_complete(
                self._create_db_records(
                    output_layer_id=output_layer_id_dests,
                    params=params,
                    output_name=output_name_dests,
                    metadata=dests_metadata,
                    table_info=table_info_dests,
                )
            )

        asyncio.get_event_loop().run_until_complete(self._close_db_service())

        # Build wm_labels
        wm_labels: list[str] = []
        if params.triggered_by_email:
            wm_labels.append(params.triggered_by_email)

        # Primary output: matrix table
        output_matrix = ToolOutputBase(
            layer_id=output_layer_id_matrix,
            name=output_name_matrix,
            folder_id=result_info_matrix["folder_id"],
            user_id=params.user_id,
            project_id=params.project_id,
            layer_project_id=result_info_matrix.get("layer_project_id"),
            type="table",
            feature_layer_type="tool",
            table_name=table_info_matrix["table_name"],
            wm_labels=wm_labels,
        )

        # Secondary output: destination points
        output_dests = ToolOutputBase(
            layer_id=output_layer_id_dests,
            name=output_name_dests,
            folder_id=result_info_dests["folder_id"],
            user_id=params.user_id,
            project_id=params.project_id,
            layer_project_id=result_info_dests.get("layer_project_id"),
            type="feature",
            feature_layer_type="tool",
            geometry_type=table_info_dests.get("geometry_type"),
            feature_count=table_info_dests.get("feature_count", 0),
            extent=table_info_dests.get("extent"),
            table_name=table_info_dests["table_name"],
            wm_labels=wm_labels,
        )

        logger.info(
            f"Tool completed: matrix={output_layer_id_matrix}, dests={output_layer_id_dests}"
        )

        result = output_matrix.model_dump()
        result["secondary_layers"] = [output_dests.model_dump()]
        return result


def main(params: TravelCostMatrixWindmillParams) -> dict:
    """Windmill entry point for travel cost matrix tool."""
    runner = TravelCostMatrixToolRunner()
    runner.init_from_env()

    try:
        return runner.run(params)
    finally:
        runner.cleanup()
