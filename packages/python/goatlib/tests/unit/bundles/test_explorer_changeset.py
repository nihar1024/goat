"""Saving the Explorer's edits to a bundle: a change set applied to the mini
feed's tables (``tests/fixtures/explorer_mini_gtfs``; see the snapshot tests
for what it holds). The feed carries two problems of its own — U2 calls at a
stop that does not exist, Z1 runs on a route that does not — which no change
here is blamed for."""

import zipfile
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import pytest
from goatlib.bundles.explorer.changeset import (
    ChangeSet,
    ChangeSetError,
    ChangeSetIntegrityError,
    apply_changeset,
)
from goatlib.bundles.importers.pt_network.gtfs import GtfsImporter
from goatlib.bundles.importers.pt_network.stop_chains import stop_chain_id
from pydantic import ValidationError

FIXTURE = Path(__file__).parents[2] / "fixtures" / "explorer_mini_gtfs"


@pytest.fixture(scope="module")
def layers(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, str]:
    root = tmp_path_factory.mktemp("changeset")
    archive = root / "mini_gtfs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for f in sorted(FIXTURE.iterdir()):
            zf.write(f, f.name)
    work = root / "work"
    work.mkdir()
    return {
        layer.role: layer.file_path
        for layer in GtfsImporter().extract_layers(str(archive), str(work))
    }


@pytest.fixture
def con(layers: Dict[str, str]) -> duckdb.DuckDBPyConnection:
    """The feed's member tables, each a plain table named for its role."""
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial")
    for role, path in layers.items():
        c.execute(f"CREATE TABLE {role} AS SELECT * FROM read_parquet('{path}')")
    return c


TABLES = {
    r: r
    for r in (
        "agency",
        "stops",
        "routes",
        "trips",
        "stop_times",
        "calendar",
        "calendar_dates",
        "frequencies",
        "shapes",
        "shape_lines",
    )
}


def apply(con: duckdb.DuckDBPyConnection, ops: List[Dict[str, Any]]) -> Any:
    return apply_changeset(con, TABLES, ChangeSet(ops=ops))


def one(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    return con.execute(sql).fetchone()


def line(con: duckdb.DuckDBPyConnection, shape_id: str) -> Any:
    row = one(
        con,
        f"SELECT ST_AsText(geometry) FROM shape_lines WHERE shape_id = '{shape_id}'",
    )
    return row[0] if row else None


def chain(stop_ids: List[str]) -> str:
    return stop_chain_id(stop_ids)


def test_a_stop_is_renamed(con: duckdb.DuckDBPyConnection) -> None:
    applied = apply(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S2"},
                "values": {"stop_name": "Second Street"},
            }
        ],
    )
    assert one(con, "SELECT stop_name FROM stops WHERE stop_id = 'S2'") == (
        "Second Street",
    )
    assert applied.rows == {"stops": {"inserted": 0, "updated": 1, "deleted": 0}}
    assert applied.warnings == []
    # Nothing left behind on the connection.
    assert one(con, "SELECT count(*) FROM duckdb_tables() WHERE temporary") == (0,)


def test_a_moved_stop_takes_its_geometry_and_redraws_the_lines_through_it(
    con: duckdb.DuckDBPyConnection,
) -> None:
    t3 = chain(["S5", "S4", "S3", "S2", "S1"])
    assert "13.42 52.5" in line(con, t3)
    apply(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S3"},
                "values": {"stop_lat": 52.51, "stop_lon": 13.425},
            }
        ],
    )
    assert one(con, "SELECT ST_AsText(geometry) FROM stops WHERE stop_id = 'S3'") == (
        "POINT (13.425 52.51)",
    )
    # T3 has no shape: its line runs through its stops, S3 now elsewhere.
    assert "13.425 52.51" in line(con, t3)
    # SH1 is drawn from its own points and does not move with a stop.
    assert "13.425" not in line(con, "SH1")


def test_a_new_stop_written_twice_is_one_insert(con: duckdb.DuckDBPyConnection) -> None:
    applied = apply(
        con,
        [
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "N1"},
                "values": {
                    "stop_name": "New",
                    "stop_lat": "52.52",
                    "stop_lon": "13.43",
                    "location_type": 0,
                },
            },
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "N1"},
                "values": {"stop_name": "Newer"},
            },
        ],
    )
    assert applied.rows["stops"] == {"inserted": 1, "updated": 0, "deleted": 0}
    assert one(
        con, "SELECT stop_name, ST_AsText(geometry) FROM stops WHERE stop_id = 'N1'"
    ) == (
        "Newer",
        "POINT (13.43 52.52)",
    )


def test_an_optional_field_the_feed_left_out_gets_its_column(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # The mini feed has no wheelchair_boarding: a value adds the column, typed
    # as an import types it; an empty value for it is no value, not an error.
    cols = lambda: {r[0]: r[1] for r in con.execute("DESCRIBE stops").fetchall()}  # noqa: E731
    assert "wheelchair_boarding" not in cols()
    apply(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S3"},
                "values": {"stop_name": "Third", "wheelchair_boarding": None},
            }
        ],
    )
    assert "wheelchair_boarding" not in cols()
    apply(
        con,
        [
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "goat_0000002a"},
                "values": {
                    "stop_name": "New",
                    "stop_lat": 52.51,
                    "stop_lon": 13.41,
                    "location_type": 0,
                    "wheelchair_boarding": 1,
                },
            }
        ],
    )
    assert cols()["wheelchair_boarding"] == "INTEGER"
    assert one(
        con,
        "SELECT wheelchair_boarding, ST_AsText(geometry) FROM stops "
        "WHERE stop_id = 'goat_0000002a'",
    ) == (1, "POINT (13.41 52.51)")


def test_a_stop_s_gtfs_fields_get_their_columns(con: duckdb.DuckDBPyConnection) -> None:
    # An entrance to the station, with what the Explorer lets a stop say.
    apply(
        con,
        [
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "E1"},
                "values": {
                    "stop_name": "Main Station, north exit",
                    "stop_lat": 52.501,
                    "stop_lon": 13.4,
                    "location_type": 2,
                    "parent_station": "P",
                },
            },
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S1"},
                "values": {"platform_code": "1"},
            },
        ],
    )
    assert one(
        con,
        "SELECT location_type, parent_station FROM stops WHERE stop_id = 'E1'",
    ) == (2, "P")
    assert one(con, "SELECT platform_code FROM stops WHERE stop_id = 'S1'") == ("1",)


def refused(con: duckdb.DuckDBPyConnection, ops: List[Dict[str, Any]]) -> Any:
    """The problems a refused change set names, rolled back as geoapi does."""
    con.begin()
    with pytest.raises(ChangeSetIntegrityError) as caught:
        apply(con, ops)
    con.rollback()
    return {(n.code, dict(n.key)["stop_id"]) for n in caught.value.notices}


def test_an_entrance_needs_its_station(con: duckdb.DuckDBPyConnection) -> None:
    entrance = {
        "role": "stops",
        "op": "insert",
        "key": {"stop_id": "E1"},
        "values": {
            "stop_name": "Exit",
            "stop_lat": 52.5,
            "stop_lon": 13.4,
            "location_type": 2,
        },
    }
    assert refused(con, [entrance]) == {("location_without_parent_station", "E1")}
    # A stop is no station to hang it from.
    entrance["values"] = {**entrance["values"], "parent_station": "S2"}
    assert refused(con, [entrance]) == {("wrong_parent_location_type", "E1")}


def test_a_station_has_no_parent(con: duckdb.DuckDBPyConnection) -> None:
    assert refused(
        con,
        [
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "P2"},
                "values": {
                    "stop_name": "Another station",
                    "stop_lat": 52.5,
                    "stop_lon": 13.4,
                    "location_type": 1,
                    "parent_station": "P",
                },
            }
        ],
    ) == {("station_with_parent_station", "P2")}


def test_a_station_made_a_stop_strands_its_platforms(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # S1 is P's platform: P no longer a station, S1's parent is the wrong kind.
    assert refused(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "P"},
                "values": {"location_type": 0},
            }
        ],
    ) == {("wrong_parent_location_type", "S1")}


def test_a_served_stop_stays_a_stop(con: duckdb.DuckDBPyConnection) -> None:
    assert refused(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S4"},
                "values": {"location_type": 1},
            }
        ],
    ) == {("location_with_unexpected_stop_time", "S4")}
    # An unserved one may become a station.
    apply(
        con,
        [
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "X"},
                "values": {"location_type": 1},
            }
        ],
    )
    assert one(con, "SELECT location_type FROM stops WHERE stop_id = 'X'") == (1,)


def test_a_row_inserted_then_deleted_leaves_no_trace(
    con: duckdb.DuckDBPyConnection,
) -> None:
    before = one(con, "SELECT count(*) FROM stops")
    applied = apply(
        con,
        [
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "N1"},
                "values": {"stop_name": "New", "stop_lat": 52.5, "stop_lon": 13.4},
            },
            {"role": "stops", "op": "delete", "key": {"stop_id": "N1"}},
        ],
    )
    assert one(con, "SELECT count(*) FROM stops") == before
    assert applied.rows == {}


def test_a_trip_goes_with_its_stop_times(con: duckdb.DuckDBPyConnection) -> None:
    ops = [{"role": "trips", "op": "delete", "key": {"trip_id": "T2"}}] + [
        {
            "role": "stop_times",
            "op": "delete",
            "key": {"trip_id": "T2", "stop_sequence": s},
        }
        for s in range(1, 6)
    ]
    applied = apply(con, ops)
    assert applied.rows["stop_times"]["deleted"] == 5
    assert one(con, "SELECT count(*) FROM stop_times WHERE trip_id = 'T2'") == (0,)


def test_a_trip_without_its_stop_times_is_refused(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(ChangeSetIntegrityError) as refused:
        apply(con, [{"role": "trips", "op": "delete", "key": {"trip_id": "T2"}}])
    codes = {(n.code, n.role, n.field) for n in refused.value.notices}
    assert codes == {("foreign_key_violation", "stop_times", "trip_id")}
    assert len(refused.value.notices) == 5


def test_a_stop_still_served_cannot_go(con: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ChangeSetIntegrityError) as refused:
        apply(con, [{"role": "stops", "op": "delete", "key": {"stop_id": "S4"}}])
    assert {n.code for n in refused.value.notices} == {"foreign_key_violation"}
    assert {dict(n.key)["trip_id"] for n in refused.value.notices} == {
        "T1",
        "T2",
        "T3",
        "F1",
        "F2",
    }


def test_a_stop_time_before_the_previous_departure_is_refused(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(ChangeSetIntegrityError) as refused:
        apply(
            con,
            [
                {
                    "role": "stop_times",
                    "op": "update",
                    "key": {"trip_id": "T1", "stop_sequence": 3},
                    "values": {
                        "arrival_time": "08:01:00",
                        "departure_time": "08:01:00",
                    },
                }
            ],
        )
    assert [(n.code, dict(n.key)) for n in refused.value.notices] == [
        (
            "stop_time_with_arrival_before_previous_departure_time",
            {"trip_id": "T1", "stop_sequence": 3},
        ),
    ]


def test_times_past_midnight_are_times(con: duckdb.DuckDBPyConnection) -> None:
    apply(
        con,
        [
            {
                "role": "stop_times",
                "op": "update",
                "key": {"trip_id": "U1", "stop_sequence": 2},
                "values": {"arrival_time": "24:12:00", "departure_time": "24:12:00"},
            }
        ],
    )
    assert one(
        con,
        "SELECT epoch(arrival_time) FROM stop_times WHERE trip_id = 'U1' AND stop_sequence = 2",
    ) == (24 * 3600 + 12 * 60,)


def test_problems_the_feed_already_had_are_not_the_change_s(
    con: duckdb.DuckDBPyConnection,
) -> None:
    # U2 calls at NOPE, which does not exist; renaming its headsign is fine.
    applied = apply(
        con,
        [
            {
                "role": "trips",
                "op": "update",
                "key": {"trip_id": "U2"},
                "values": {"trip_headsign": "Second St"},
            }
        ],
    )
    assert applied.rows["trips"]["updated"] == 1


def test_a_trip_given_another_stop_gets_a_new_line(
    con: duckdb.DuckDBPyConnection,
) -> None:
    old = chain(["S5", "S4", "S3", "S2", "S1"])
    new = chain(["S5", "S4", "S3", "S2", "S1", "S6"])
    # T3, which has no shape, runs on past S1 (08:28) to S6.
    apply(
        con,
        [
            {
                "role": "stop_times",
                "op": "insert",
                "key": {"trip_id": "T3", "stop_sequence": 6},
                "values": {
                    "stop_id": "S6",
                    "arrival_time": "08:35:00",
                    "departure_time": "08:35:00",
                },
            }
        ],
    )
    assert line(con, new) is not None
    # No other trip ran T3's old stops: its line goes.
    assert line(con, old) is None


def test_a_shape_point_moved_redraws_the_shape(con: duckdb.DuckDBPyConnection) -> None:
    apply(
        con,
        [
            {
                "role": "shapes",
                "op": "update",
                "key": {"shape_id": "SH1", "shape_pt_sequence": 2},
                "values": {"shape_pt_lat": 52.51},
            }
        ],
    )
    assert "13.405 52.51" in line(con, "SH1")


def test_a_trip_left_with_one_stop_is_a_warning(con: duckdb.DuckDBPyConnection) -> None:
    applied = apply(
        con,
        [
            {
                "role": "stop_times",
                "op": "delete",
                "key": {"trip_id": "Z1", "stop_sequence": 2},
            },
        ],
    )
    assert [n.code for n in applied.warnings] == ["unusable_trip"]


@pytest.mark.parametrize(
    "op, message",
    [
        (
            {
                "role": "stop_times",
                "op": "update",
                "key": {"trip_id": "T1", "stop_sequence": 1},
                "values": {"arrival_time": "8 o'clock"},
            },
            "not a valid GTFS time",
        ),
        (
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "S1"},
                "values": {"stop_flavour": "sweet"},
            },
            "has no column stop_flavour",
        ),
        (
            {
                "role": "stops",
                "op": "update",
                "key": {"stop_id": "GONE"},
                "values": {"stop_name": "x"},
            },
            "is not there",
        ),
        (
            {
                "role": "stops",
                "op": "insert",
                "key": {"stop_id": "S1"},
                "values": {"stop_name": "again"},
            },
            "already exists",
        ),
        (
            {
                "role": "calendar_dates",
                "op": "insert",
                "key": {"service_id": "WK", "date": "2026-04-07"},
                "values": {"exception_type": 2},
            },
            "not a valid GTFS date",
        ),
    ],
)
def test_a_malformed_change_set_is_refused_whole(
    con: duckdb.DuckDBPyConnection, op: Dict[str, Any], message: str
) -> None:
    before = one(con, "SELECT count(*), max(stop_name) FROM stops")
    with pytest.raises(ChangeSetError, match=message):
        apply(con, [op])
    assert one(con, "SELECT count(*), max(stop_name) FROM stops") == before


@pytest.mark.parametrize(
    "op",
    [
        {"role": "shape_lines", "op": "delete", "key": {"shape_id": "SH1"}},
        {
            "role": "stops",
            "op": "update",
            "key": {"stop_id": "S1"},
            "values": {"geometry": "POINT (0 0)"},
        },
        {
            "role": "stop_times",
            "op": "update",
            "key": {"trip_id": "T1"},
            "values": {"stop_id": "S2"},
        },
        {
            "role": "stops",
            "op": "update",
            "key": {"stop_id": "S1"},
            "values": {"stop_id": "S9"},
        },
    ],
)
def test_what_a_change_set_may_not_say(op: Dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ChangeSet(ops=[op])
