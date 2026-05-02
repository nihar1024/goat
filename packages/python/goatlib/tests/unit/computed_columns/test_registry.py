from goatlib.computed_columns import (
    COMPUTED_KIND_REGISTRY,
    ComputedKind,
    get_computed_kind,
    is_computed_kind,
)


def test_registry_is_dict() -> None:
    assert isinstance(COMPUTED_KIND_REGISTRY, dict)


def test_get_computed_kind_returns_entry_for_known_name() -> None:
    # Built-in kinds will be added in subsequent tasks; here we only
    # check that a missing kind returns None.
    assert get_computed_kind("does_not_exist") is None


def test_is_computed_kind_returns_false_for_non_computed() -> None:
    assert is_computed_kind("string") is False
    assert is_computed_kind("number") is False
    assert is_computed_kind("does_not_exist") is False


def test_computed_kind_dataclass_fields() -> None:
    kind = ComputedKind(
        name="dummy",
        duckdb_type="DOUBLE",
        allowed_geom_types=frozenset({"polygon"}),
        depends_on=("geometry",),
        compute_sql_template="ST_Dummy({geom})",
    )
    assert kind.name == "dummy"
    assert kind.duckdb_type == "DOUBLE"
    assert kind.allowed_geom_types == frozenset({"polygon"})
    assert kind.depends_on == ("geometry",)
    assert kind.compute_sql("geometry") == 'ST_Dummy("geometry")'


def test_compute_sql_quotes_identifier() -> None:
    kind = ComputedKind(
        name="dummy",
        duckdb_type="DOUBLE",
        allowed_geom_types=frozenset({"polygon"}),
        depends_on=("geometry",),
        compute_sql_template="ST_Dummy({geom})",
    )
    # Quote the geom column safely
    assert kind.compute_sql("geom") == 'ST_Dummy("geom")'


def test_area_kind_registered() -> None:
    kind = get_computed_kind("area")
    assert kind is not None
    assert kind.duckdb_type == "DOUBLE"
    assert kind.allowed_geom_types == frozenset({"polygon", "multipolygon"})
    assert kind.depends_on == ("geometry",)
    assert kind.compute_sql("geometry") == 'ST_Area_Spheroid("geometry")'


def test_perimeter_kind_registered() -> None:
    kind = get_computed_kind("perimeter")
    assert kind is not None
    assert kind.duckdb_type == "DOUBLE"
    assert kind.allowed_geom_types == frozenset({"polygon", "multipolygon"})
    assert kind.depends_on == ("geometry",)
    assert kind.compute_sql("geometry") == 'ST_Perimeter_Spheroid("geometry")'


def test_length_kind_registered() -> None:
    kind = get_computed_kind("length")
    assert kind is not None
    assert kind.duckdb_type == "DOUBLE"
    assert kind.allowed_geom_types == frozenset({"line", "multiline"})
    assert kind.depends_on == ("geometry",)
    assert kind.compute_sql("geometry") == 'ST_Length_Spheroid("geometry")'


def test_is_computed_kind_true_for_built_ins() -> None:
    assert is_computed_kind("area")
    assert is_computed_kind("perimeter")
    assert is_computed_kind("length")
