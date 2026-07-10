"""Tests for the single `datetime` temporal field-kind."""

from geoapi.routers.features_write import _resolve_kind_to_sql
from geoapi.routers.metadata import _kind_from_json_type
from geoapi.services.layer_service import LayerService


class TestDuckDBFormat:
    """Temporal DuckDB types collapse to a single OGC `date-time` format."""

    def test_date_collapses_to_datetime(self):
        assert LayerService._duckdb_to_json_format("DATE") == "date-time"

    def test_timestamp_format(self):
        assert LayerService._duckdb_to_json_format("TIMESTAMP") == "date-time"
        assert (
            LayerService._duckdb_to_json_format("TIMESTAMP WITH TIME ZONE")
            == "date-time"
        )

    def test_time_is_excluded(self):
        # Time-of-day is not temporal -> no format (falls through to string).
        assert LayerService._duckdb_to_json_format("TIME") is None

    def test_non_temporal_has_no_format(self):
        assert LayerService._duckdb_to_json_format("VARCHAR") is None
        assert LayerService._duckdb_to_json_format("DOUBLE") is None

    def test_temporal_json_type_stays_string(self):
        assert LayerService._duckdb_to_json_type("DATE") == "string"
        assert LayerService._duckdb_to_json_type("TIMESTAMP") == "string"


class TestKindFromJsonType:
    """Kind inference maps the OGC `date-time` format to `datetime`."""

    def test_datetime_format_infers_datetime(self):
        assert _kind_from_json_type("string", "date-time") == "datetime"

    def test_number_without_format(self):
        assert _kind_from_json_type("number") == "number"

    def test_string_without_format(self):
        assert _kind_from_json_type("string") == "string"


class TestResolveKindToSql:
    """`datetime` resolves to a physical TIMESTAMP WITH TIME ZONE, not computed."""

    def test_datetime_kind(self):
        duckdb_type, compute_sql, depends_on, computed = _resolve_kind_to_sql(
            "datetime", None, None
        )
        assert duckdb_type == "TIMESTAMP WITH TIME ZONE"
        assert compute_sql is None
        assert depends_on == []
        assert computed is False
