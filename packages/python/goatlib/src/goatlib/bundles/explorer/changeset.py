"""Saving the Explorer's edits: a change set of GTFS rows, applied to a bundle.

The Explorer edits a bundle in the browser, on its own copy (the snapshot).
On save it sends what changed as rows of the bundle's GTFS tables, keyed by
GTFS ids — never by the snapshot's indexes, which are only valid within one
build. This module applies such a change set to the member tables, in the
caller's transaction, and keeps the bundle whole:

- **Values are GTFS text**, typed by the importer's own rules
  (``importers.pt_network.gtfs_schema``): a time ``25:10:00``, a date
  ``20261012``, numbers as numbers. A value that does not parse is refused.
- **Operations on one row are squashed** first: an insert later updated is
  one insert, an insert later deleted is nothing. Updating a row inserted in
  the same DuckLake transaction leaves it a transaction-local row id, which
  breaks the tiles drawn from it, so no row is written twice.
- **What the bundle derives is kept in step**: a stop's ``geometry`` from its
  coordinates, and ``shape_lines`` — the lines the map draws — for every shape
  and every shapeless trip the change touches (``importers.pt_network
  .stop_chains`` is the rule for the latter).
- **Integrity is checked on what the change touches**, with the MobilityData
  validator's notice codes. Only problems the change introduces count: a row
  that was already wrong before is not this change's to answer for. Any new
  ERROR refuses the whole change set (``ChangeSetIntegrityError``); the caller rolls
  back.

Nothing here knows where the tables live: ``tables`` maps each role to a SQL
table name (a DuckLake table in geoapi, a plain DuckDB table in tests).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

from pydantic import BaseModel, Field, model_validator

from goatlib.bundles.importers.pt_network.gtfs_schema import SCHEMA
from goatlib.bundles.importers.pt_network.stop_chains import STOP_CHAIN_PREFIX

#: The roles a change set may write, each with its GTFS primary key.
ROLE_KEYS: Dict[str, Tuple[str, ...]] = {
    "agency": ("agency_id",),
    "stops": ("stop_id",),
    "routes": ("route_id",),
    "trips": ("trip_id",),
    "stop_times": ("trip_id", "stop_sequence"),
    "calendar": ("service_id",),
    "calendar_dates": ("service_id", "date"),
    "frequencies": ("trip_id", "start_time"),
    "shapes": ("shape_id", "shape_pt_sequence"),
}

#: Columns a client never writes: the bundle derives them.
DERIVED_COLUMNS = frozenset({"geometry", "bbox", "xmin", "ymin", "xmax", "ymax"})

Value = Union[str, int, float, None]
Severity = Literal["ERROR", "WARNING", "INFO"]

#: Spliced into a write: ``(role, table columns, geometry SQL)`` → the
#: columns the layer derives from its geometry (bbox, computed columns), each
#: as ``(column, SQL)``. geoapi supplies it from the layer's field config.
Derived = Callable[[str, Sequence[str], str], List[Tuple[str, str]]]


class ChangeSetError(ValueError):
    """The change set itself is malformed: an unknown role or column, a value
    that does not parse, a row it updates that is not there."""


class RowOp(BaseModel):
    """One row written: inserted whole, updated in the columns given, or
    deleted. ``key`` names the row by its GTFS primary key."""

    role: str
    op: Literal["insert", "update", "delete"]
    key: Dict[str, Value]
    values: Dict[str, Value] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _shape(self) -> "RowOp":
        keys = ROLE_KEYS.get(self.role)
        if keys is None:
            raise ValueError(f"{self.role} is not a table the Explorer edits")
        if set(self.key) != set(keys):
            raise ValueError(f"a {self.role} row is keyed by {', '.join(keys)}")
        if self.op == "delete" and self.values:
            raise ValueError("a delete carries no values")
        if self.op == "update" and not self.values:
            raise ValueError("an update names the columns it sets")
        named = set(self.values)
        if named & set(keys):
            raise ValueError(
                "a key column is changed by deleting and inserting the row"
            )
        if named & DERIVED_COLUMNS:
            raise ValueError(
                f"{', '.join(sorted(named & DERIVED_COLUMNS))} is derived, never written"
            )
        return self


class ChangeSet(BaseModel):
    """The rows a session changed, in the order it changed them."""

    ops: List[RowOp] = Field(..., min_length=1, max_length=500_000)


@dataclass(frozen=True)
class Notice:
    """One finding, as the MobilityData validator names it."""

    code: str
    severity: Severity
    role: str
    key: Tuple[Tuple[str, Any], ...]
    field: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "role": self.role,
            "key": {k: _jsonable(v) for k, v in self.key},
            "field": self.field,
        }


class ChangeSetIntegrityError(Exception):
    """The change set would leave the bundle with an ERROR."""

    def __init__(self, notices: List[Notice]) -> None:
        super().__init__(
            f"{len(notices)} problem(s): "
            + "; ".join(f"{n.code} in {n.role}" for n in notices[:5])
        )
        self.notices = notices


@dataclass
class Applied:
    """What a change set did: rows per role, and the warnings it brought."""

    rows: Dict[str, Dict[str, int]] = field(default_factory=dict)
    warnings: List[Notice] = field(default_factory=list)


# --------------------------------------------------------------------------
# Values


_INT = re.compile(r"-?[0-9]+")
_DATE = re.compile(r"[0-9]{8}")
_TIME = re.compile(r"([0-9]{1,3}):([0-9]{1,2}):([0-9]{1,2})")


def _typed(role: str, column: str, value: Value) -> Any:
    """``value`` as the column stores it; empty is no value."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    spec = SCHEMA.get(role, {}).get(column)
    kind = spec.kind if spec else "text"
    text = value.strip() if isinstance(value, str) else value
    try:
        if kind == "integer":
            if isinstance(text, bool):
                raise ValueError
            if isinstance(text, int):
                return text
            if isinstance(text, str) and _INT.fullmatch(text):
                return int(text)
            raise ValueError
        if kind == "double":
            number = float(text)  # type: ignore[arg-type]
            if number != number or number in (float("inf"), float("-inf")):
                raise ValueError
            return number
        if kind == "date":
            if not isinstance(text, str) or not _DATE.fullmatch(text):
                raise ValueError
            return date(int(text[:4]), int(text[4:6]), int(text[6:]))
        if kind == "time":
            m = _TIME.fullmatch(text) if isinstance(text, str) else None
            if not m or int(m[2]) > 59 or int(m[3]) > 59:
                raise ValueError
            return timedelta(hours=int(m[1]), minutes=int(m[2]), seconds=int(m[3]))
    except (TypeError, ValueError):
        raise ChangeSetError(
            f"{role}.{column}: {value!r} is not a valid GTFS {kind}"
        ) from None
    if not isinstance(text, str):
        raise ChangeSetError(f"{role}.{column}: {value!r} is text in GTFS")
    return text


def _jsonable(value: Any) -> Any:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    if isinstance(value, timedelta):
        s = int(value.total_seconds())
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return value


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# --------------------------------------------------------------------------
# Squashing


@dataclass
class _Net:
    """The net effect of a change set on one row."""

    kind: Literal["insert", "update", "delete", "replace"]
    values: Dict[str, Any]


def _squash(
    ops: Iterable[Tuple[str, str, Tuple[Any, ...], Dict[str, Any]]],
) -> Dict[str, Dict[Tuple[Any, ...], _Net]]:
    """One net write per row, from ``(role, op, key, values)`` in order."""
    out: Dict[str, Dict[Tuple[Any, ...], _Net]] = {}
    for role, op, key, values in ops:
        rows = out.setdefault(role, {})
        prev = rows.get(key)
        where = f"{role} {dict(zip(ROLE_KEYS[role], key))}"
        if prev is None:
            rows[key] = _Net(op, dict(values))  # type: ignore[arg-type]
        elif op == "insert":
            if prev.kind != "delete":
                raise ChangeSetError(f"{where} is inserted while it exists")
            rows[key] = _Net("replace", dict(values))
        elif op == "update":
            if prev.kind == "delete":
                raise ChangeSetError(f"{where} is updated after it was deleted")
            prev.values.update(values)
        elif prev.kind == "insert":  # delete after insert: nothing at all
            del rows[key]
        elif prev.kind == "delete":
            raise ChangeSetError(f"{where} is deleted twice")
        else:  # delete after update or replace
            rows[key] = _Net("delete", {})
    return out


# --------------------------------------------------------------------------
# Applying


class _Tables:
    """The tables written, with their columns, read once."""

    def __init__(self, con: Any, tables: Mapping[str, str]) -> None:
        self.con = con
        self.names = dict(tables)
        self._columns: Dict[str, List[str]] = {}

    def has(self, role: str) -> bool:
        return role in self.names

    def name(self, role: str) -> str:
        if role not in self.names:
            raise ChangeSetError(f"the bundle has no {role} table")
        return self.names[role]

    def columns(self, role: str) -> List[str]:
        if role not in self._columns:
            self._columns[role] = [
                str(r[0])
                for r in self.con.execute(f"DESCRIBE {self.name(role)}").fetchall()
            ]
        return self._columns[role]

    def types(self, role: str) -> Dict[str, str]:
        return {
            str(r[0]): str(r[1]).upper()
            for r in self.con.execute(f"DESCRIBE {self.name(role)}").fetchall()
        }


def _parse_ops(
    t: _Tables, changeset: ChangeSet
) -> List[Tuple[str, str, Tuple[Any, ...], Dict[str, Any]]]:
    parsed: List[Tuple[str, str, Tuple[Any, ...], Dict[str, Any]]] = []
    for op in changeset.ops:
        columns = set(t.columns(op.role))
        unknown = sorted(set(op.values) - columns)
        if unknown:
            raise ChangeSetError(f"{op.role} has no column {', '.join(unknown)}")
        key = tuple(_typed(op.role, k, op.key[k]) for k in ROLE_KEYS[op.role])
        if any(k is None for k in key):
            raise ChangeSetError(f"a {op.role} key is empty")
        values = {c: _typed(op.role, c, v) for c, v in op.values.items()}
        parsed.append((op.role, op.op, key, values))
    return parsed


def _where(role: str, key: Tuple[Any, ...], params: Dict[str, Any]) -> str:
    parts = []
    for i, (col, value) in enumerate(zip(ROLE_KEYS[role], key)):
        params[f"k{i}"] = value
        parts.append(f"{_ident(col)} = $k{i}")
    return " AND ".join(parts)


def _exists(t: _Tables, role: str, key: Tuple[Any, ...]) -> bool:
    params: Dict[str, Any] = {}
    sql = f"SELECT count(*) FROM {t.name(role)} WHERE {_where(role, key, params)}"
    return bool(t.con.execute(sql, params).fetchone()[0])


def _geometry_sql(role: str, set_exprs: Mapping[str, str]) -> Optional[str]:
    """The geometry a stop takes from its coordinates, spelled from what the
    statement sets (``set_exprs``) or else the row's own columns."""
    if role != "stops":
        return None
    lon = set_exprs.get("stop_lon", '"stop_lon"')
    lat = set_exprs.get("stop_lat", '"stop_lat"')
    return (
        f"CASE WHEN {lon} IS NOT NULL AND {lat} IS NOT NULL "
        f"THEN ST_Point({lon}, {lat}) END"
    )


def _derived_exprs(
    t: _Tables, role: str, geom: str, derived: Optional[Derived]
) -> List[Tuple[str, str]]:
    columns = t.columns(role)
    exprs = [("geometry", geom)] if "geometry" in columns else []
    if derived and exprs:
        exprs += derived(role, columns, f"({geom})")
    return exprs


def _insert(
    t: _Tables,
    role: str,
    key: Tuple[Any, ...],
    values: Mapping[str, Any],
    derived: Optional[Derived],
) -> None:
    params: Dict[str, Any] = {}
    cols, exprs = [], []
    for i, (col, value) in enumerate(
        list(zip(ROLE_KEYS[role], key)) + list(values.items())
    ):
        params[f"v{i}"] = value
        cols.append(col)
        exprs.append(f"$v{i}")
    if role == "stops":
        # A new row has no columns of its own to fall back on.
        given = dict(zip(cols, exprs))
        geom = _geometry_sql(
            role,
            {c: given.get(c, "CAST(NULL AS DOUBLE)") for c in ("stop_lon", "stop_lat")},
        )
        assert geom is not None
        for col, sql in _derived_exprs(t, role, geom, derived):
            cols.append(col)
            exprs.append(sql)
    t.con.execute(
        f"INSERT INTO {t.name(role)} ({', '.join(_ident(c) for c in cols)}) "
        f"VALUES ({', '.join(exprs)})",
        params,
    )


def _update(
    t: _Tables,
    role: str,
    key: Tuple[Any, ...],
    values: Mapping[str, Any],
    derived: Optional[Derived],
) -> None:
    params: Dict[str, Any] = {}
    sets = []
    set_exprs: Dict[str, str] = {}
    for i, (col, value) in enumerate(values.items()):
        params[f"v{i}"] = value
        set_exprs[col] = f"$v{i}"
        sets.append(f"{_ident(col)} = $v{i}")
    if role == "stops" and {"stop_lon", "stop_lat"} & set(values):
        geom = _geometry_sql(role, set_exprs)
        assert geom is not None
        for col, sql in _derived_exprs(t, role, geom, derived):
            sets.append(f"{_ident(col)} = {sql}")
    t.con.execute(
        f"UPDATE {t.name(role)} SET {', '.join(sets)} "
        f"WHERE {_where(role, key, params)}",
        params,
    )


def _delete(t: _Tables, role: str, key: Tuple[Any, ...]) -> None:
    params: Dict[str, Any] = {}
    t.con.execute(
        f"DELETE FROM {t.name(role)} WHERE {_where(role, key, params)}", params
    )


# --------------------------------------------------------------------------
# What the change touches


@dataclass
class _Touched:
    keys: Dict[str, Set[Tuple[Any, ...]]]

    def ids(self, role: str, column: str) -> Set[Any]:
        i = ROLE_KEYS[role].index(column)
        return {k[i] for k in self.keys.get(role, set())}

    @property
    def trips(self) -> Set[Any]:
        return (
            self.ids("trips", "trip_id")
            | self.ids("stop_times", "trip_id")
            | self.ids("frequencies", "trip_id")
        )

    @property
    def services(self) -> Set[Any]:
        return self.ids("calendar", "service_id") | self.ids(
            "calendar_dates", "service_id"
        )


def _id_table(con: Any, name: str, ids: Iterable[Any]) -> str:
    """A temp table of ``ids`` (text), for joining against."""
    con.execute(f"CREATE OR REPLACE TEMP TABLE {name} (id VARCHAR)")
    rows = [(str(i),) for i in ids]
    if rows:
        con.executemany(f"INSERT INTO {name} VALUES (?)", rows)
    return name


# --------------------------------------------------------------------------
# Integrity


#: Fields the GTFS reference requires without condition, per role (keys
#: aside: those are never empty). Conditionally required ones are checked
#: on their own below.
_REQUIRED: Dict[str, Tuple[str, ...]] = {
    "agency": ("agency_name", "agency_url", "agency_timezone"),
    "routes": ("route_type",),
    "trips": ("route_id", "service_id"),
    "stop_times": ("stop_id",),
    "calendar": (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ),
    "calendar_dates": ("exception_type",),
    "frequencies": ("end_time", "headway_secs"),
    "shapes": ("shape_pt_lat", "shape_pt_lon"),
}


def _blank(column: str) -> str:
    col = _ident(column)
    return f"({col} IS NULL OR CAST({col} AS VARCHAR) = '')"


def _check(t: _Tables, touched: _Touched) -> Set[Notice]:
    """The ERRORs and WARNINGs on what ``touched`` reaches: its rows, and the
    rows referring to them."""
    con = t.con
    notices: Set[Notice] = set()

    def add(
        code: str,
        severity: Severity,
        role: str,
        rows: Iterable[Sequence[Any]],
        field: Optional[str] = None,
    ) -> None:
        for row in rows:
            key = tuple(zip(ROLE_KEYS[role], row))
            notices.add(Notice(code, severity, role, key, field))

    trips = _id_table(con, "_cs_trips", touched.trips)
    stops = _id_table(con, "_cs_stops", touched.ids("stops", "stop_id"))
    routes = _id_table(con, "_cs_routes", touched.ids("routes", "route_id"))
    services = _id_table(con, "_cs_services", touched.services)
    shapes = _id_table(con, "_cs_shapes", touched.ids("shapes", "shape_id"))
    agencies = _id_table(con, "_cs_agencies", touched.ids("agency", "agency_id"))

    def keys_sql(role: str, alias: str = "x") -> str:
        return ", ".join(f"{alias}.{_ident(k)}" for k in ROLE_KEYS[role])

    def touched_rows(role: str) -> Optional[str]:
        """``role``'s touched rows, as a WHERE on alias ``x``."""
        keys = touched.keys.get(role)
        if not keys:
            return None
        cols = ROLE_KEYS[role]
        # Each key as a JSON array of its GTFS texts, matched column by column.
        name = _id_table(
            con,
            f"_cs_rows_{role}",
            (json.dumps([_jsonable(v) for v in k]) for k in keys),
        )
        match = " AND ".join(
            f"{_text(t, role, c, 'x')} = json_extract_string(id, '$[{i}]')"
            for i, c in enumerate(cols)
        )
        return f"EXISTS (SELECT 1 FROM {name} WHERE {match})"

    # Duplicate keys among the rows written.
    for role in touched.keys:
        if not t.has(role):
            continue
        cond = touched_rows(role)
        if cond is None:
            continue
        add(
            "duplicate_key",
            "ERROR",
            role,
            con.execute(
                f"SELECT {keys_sql(role)} FROM {t.name(role)} x WHERE {cond} "
                f"GROUP BY ALL HAVING count(*) > 1"
            ).fetchall(),
        )

    # Required fields on the rows written.
    for role, fields in _REQUIRED.items():
        cond = touched_rows(role) if t.has(role) else None
        if cond is None:
            continue
        cols = set(t.columns(role))
        for f in fields:
            if f not in cols:
                continue
            add(
                "missing_required_field",
                "ERROR",
                role,
                con.execute(
                    f"SELECT {keys_sql(role)} FROM {t.name(role)} x "
                    f"WHERE {cond} AND {_blank(f)}"
                ).fetchall(),
                f,
            )
    if t.has("stops") and (cond := touched_rows("stops")) is not None:
        cols = set(t.columns("stops"))
        kind = "coalesce(location_type, 0)" if "location_type" in cols else "0"
        for f in ("stop_name", "stop_lat", "stop_lon"):
            if f not in cols:
                continue
            add(
                "missing_required_field",
                "ERROR",
                "stops",
                con.execute(
                    f"SELECT {keys_sql('stops')} FROM {t.name('stops')} x "
                    f"WHERE {cond} AND {kind} IN (0, 1, 2) AND {_blank(f)}"
                ).fetchall(),
                f,
            )
    if t.has("routes") and (cond := touched_rows("routes")) is not None:
        cols = set(t.columns("routes"))
        short = _blank("route_short_name") if "route_short_name" in cols else "true"
        long = _blank("route_long_name") if "route_long_name" in cols else "true"
        add(
            "route_both_short_and_long_name_missing",
            "ERROR",
            "routes",
            con.execute(
                f"SELECT {keys_sql('routes')} FROM {t.name('routes')} x "
                f"WHERE {cond} AND {short} AND {long}"
            ).fetchall(),
        )

    # References, from the rows written and to them.
    def foreign(
        child: str,
        column: str,
        parents: Sequence[Tuple[str, str]],
        reach: Sequence[Tuple[str, str]],
    ) -> None:
        """Rows of ``child`` whose ``column`` names nothing in ``parents``
        ((role, column) pairs), among the rows written (``child``'s own) and
        those whose ``column`` (or other columns, ``reach``) points at a
        touched id table."""
        if not t.has(child) or column not in t.columns(child):
            return
        present = [(r, c) for r, c in parents if t.has(r) and c in t.columns(r)]
        if not present:
            return
        own = touched_rows(child)
        reached = [
            f"CAST(x.{_ident(c)} AS VARCHAR) IN (SELECT id FROM {table})"
            for c, table in reach
            if c in t.columns(child)
        ]
        conds = ([own] if own else []) + reached
        if not conds:
            return
        exists = " OR ".join(
            f"EXISTS (SELECT 1 FROM {t.name(r)} p WHERE p.{_ident(c)} = x.{_ident(column)})"
            for r, c in present
        )
        add(
            "foreign_key_violation",
            "ERROR",
            child,
            con.execute(
                f"SELECT {keys_sql(child)} FROM {t.name(child)} x "
                f"WHERE ({' OR '.join(conds)}) AND NOT {_blank(column)} "
                f"AND NOT ({exists})"
            ).fetchall(),
            column,
        )

    foreign("stop_times", "trip_id", [("trips", "trip_id")], [("trip_id", trips)])
    foreign(
        "stop_times",
        "stop_id",
        [("stops", "stop_id")],
        [("trip_id", trips), ("stop_id", stops)],
    )
    foreign(
        "trips",
        "route_id",
        [("routes", "route_id")],
        [("trip_id", trips), ("route_id", routes)],
    )
    foreign(
        "trips",
        "service_id",
        [("calendar", "service_id"), ("calendar_dates", "service_id")],
        [("trip_id", trips), ("service_id", services)],
    )
    foreign(
        "trips",
        "shape_id",
        [("shapes", "shape_id")],
        [("trip_id", trips), ("shape_id", shapes)],
    )
    foreign(
        "routes",
        "agency_id",
        [("agency", "agency_id")],
        [("route_id", routes), ("agency_id", agencies)],
    )
    foreign("frequencies", "trip_id", [("trips", "trip_id")], [("trip_id", trips)])
    foreign(
        "stops",
        "parent_station",
        [("stops", "stop_id")],
        [("stop_id", stops), ("parent_station", stops)],
    )

    # Each touched trip's stop times: in order, with their times consistent.
    if t.has("stop_times") and touched.trips:
        cols = set(t.columns("stop_times"))
        if {"arrival_time", "departure_time"} <= cols:
            types = t.types("stop_times")
            arr = _as_time("arrival_time", types)
            dep = _as_time("departure_time", types)
            rows = f"""
                SELECT trip_id, stop_sequence, {arr} AS arr, {dep} AS dep,
                       row_number() OVER w AS i, count(*) OVER (PARTITION BY trip_id) AS n,
                       max({dep}) OVER (PARTITION BY trip_id ORDER BY stop_sequence
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_dep
                FROM {t.name('stop_times')}
                WHERE CAST(trip_id AS VARCHAR) IN (SELECT id FROM {trips})
                WINDOW w AS (PARTITION BY trip_id ORDER BY stop_sequence)
            """
            add(
                "stop_time_with_only_arrival_or_departure_time",
                "ERROR",
                "stop_times",
                con.execute(
                    f"SELECT trip_id, stop_sequence FROM ({rows}) "
                    "WHERE (arr IS NULL) <> (dep IS NULL)"
                ).fetchall(),
            )
            add(
                "missing_trip_edge",
                "ERROR",
                "stop_times",
                con.execute(
                    f"SELECT trip_id, stop_sequence FROM ({rows}) "
                    "WHERE (i = 1 OR i = n) AND (arr IS NULL OR dep IS NULL)"
                ).fetchall(),
            )
            add(
                "stop_time_with_arrival_before_previous_departure_time",
                "ERROR",
                "stop_times",
                con.execute(
                    f"SELECT trip_id, stop_sequence FROM ({rows}) "
                    "WHERE arr < prev_dep"
                ).fetchall(),
            )
        if t.has("trips"):
            add(
                "unusable_trip",
                "WARNING",
                "trips",
                con.execute(
                    f"""
                    SELECT x.trip_id FROM {t.name('trips')} x
                    WHERE CAST(x.trip_id AS VARCHAR) IN (SELECT id FROM {trips})
                      AND (SELECT count(*) FROM {t.name('stop_times')} st
                           WHERE st.trip_id = x.trip_id) < 2
                    """
                ).fetchall(),
            )
    return notices


def _as_time(column: str, types: Mapping[str, str]) -> str:
    """A stop time's column as an interval, whether stored typed or as text
    (a bundle imported before typing)."""
    col = _ident(column)
    if types.get(column, "").startswith("INTERVAL"):
        return col
    return f"TRY_CAST(NULLIF(trim(CAST({col} AS VARCHAR)), '') AS INTERVAL)"


def _text(t: _Tables, role: str, column: str, alias: str) -> str:
    """``alias.column`` as the text ``_jsonable`` gives for it."""
    types = t.types(role)
    col = f"{alias}.{_ident(column)}"
    kind = types.get(column, "")
    if kind == "DATE":
        return f"strftime({col}, '%Y%m%d')"
    if kind.startswith("INTERVAL"):
        s = f"CAST(epoch({col}) AS BIGINT)"
        return f"printf('%02d:%02d:%02d', {s} // 3600, ({s} % 3600) // 60, {s} % 60)"
    return f"CAST({col} AS VARCHAR)"


# --------------------------------------------------------------------------
# shape_lines


def _real_lines(t: _Tables, shape_ids: Set[Any], derived: Optional[Derived]) -> None:
    """Redraw the lines of ``shape_ids`` from their points."""
    if not shape_ids or not t.has("shape_lines"):
        return
    con = t.con
    ids = _id_table(con, "_cs_line_shapes", shape_ids)
    con.execute(
        f"DELETE FROM {t.name('shape_lines')} "
        f"WHERE CAST(shape_id AS VARCHAR) IN (SELECT id FROM {ids})"
    )
    if not t.has("shapes"):
        return
    _insert_lines(
        t,
        f"""
        SELECT shape_id,
               ST_MakeLine(list(ST_Point(shape_pt_lon, shape_pt_lat)
                                ORDER BY shape_pt_sequence, shape_pt_lon, shape_pt_lat))
                   AS geometry
        FROM {t.name('shapes')}
        WHERE CAST(shape_id AS VARCHAR) IN (SELECT id FROM {ids})
          AND shape_pt_sequence IS NOT NULL
          AND shape_pt_lon IS NOT NULL AND shape_pt_lat IS NOT NULL
        GROUP BY shape_id
        HAVING count(*) >= 2
        """,
        derived,
    )


def _insert_lines(t: _Tables, select: str, derived: Optional[Derived]) -> None:
    """Insert ``select``'s ``(shape_id, geometry)`` rows into shape_lines,
    with the columns the layer derives from geometry."""
    exprs = [("shape_id", "shape_id"), ("geometry", "geometry")]
    if derived:
        exprs += derived("shape_lines", t.columns("shape_lines"), "geometry")
    cols = ", ".join(_ident(c) for c, _ in exprs)
    t.con.execute(
        f"INSERT INTO {t.name('shape_lines')} ({cols}) "
        f"SELECT {', '.join(sql for _, sql in exprs)} FROM ({select})"
    )


def _drawn(t: _Tables) -> str:
    """SQL for the shape ids with a line of their own (two drawable points)."""
    if not t.has("shapes"):
        return "SELECT NULL::VARCHAR AS shape_id WHERE false"
    return f"""
        SELECT CAST(shape_id AS VARCHAR) AS shape_id FROM {t.name('shapes')}
        WHERE shape_pt_sequence IS NOT NULL
          AND shape_pt_lon IS NOT NULL AND shape_pt_lat IS NOT NULL
        GROUP BY shape_id HAVING count(*) >= 2
    """


def _chains(t: _Tables, trips_sql: Optional[str]) -> str:
    """SQL for ``(trip_id, shape_id)``: the stop-chain line of each
    shapeless trip among ``trips_sql`` (all shapeless trips when None), by the
    rule in ``stop_chains``."""
    trip_cols = set(t.columns("trips"))
    shape = (
        "NULLIF(CAST(tr.shape_id AS VARCHAR), '')"
        if "shape_id" in trip_cols
        else "CAST(NULL AS VARCHAR)"
    )
    among = f"AND CAST(tr.trip_id AS VARCHAR) IN ({trips_sql})" if trips_sql else ""
    return f"""
        WITH shapeless AS (
            SELECT tr.trip_id FROM {t.name('trips')} tr
            WHERE ({shape} IS NULL OR {shape} NOT IN ({_drawn(t)})) {among}
        )
        SELECT st.trip_id,
               '{STOP_CHAIN_PREFIX}' || md5(string_agg(CAST(st.stop_id AS VARCHAR), chr(31)
                                                      ORDER BY st.stop_sequence)) AS shape_id
        FROM {t.name('stop_times')} st
        JOIN shapeless USING (trip_id)
        WHERE st.stop_sequence IS NOT NULL
          AND st.stop_id IN (SELECT stop_id FROM {t.name('stops')})
        GROUP BY st.trip_id
    """


def _chain_trips(t: _Tables, touched: _Touched) -> Optional[str]:
    """SQL listing the trips whose stop-chain line the change may move: the
    trips it touches, those calling at a stop it touches, and those on a
    shape it touches."""
    if not (t.has("trips") and t.has("stop_times") and t.has("stops")):
        return None
    con = t.con
    trips = _id_table(con, "_cs_chain_trips", touched.trips)
    stops = _id_table(con, "_cs_chain_stops", touched.ids("stops", "stop_id"))
    shapes = _id_table(con, "_cs_chain_shapes", touched.ids("shapes", "shape_id"))
    on_shape = (
        f"UNION SELECT CAST(trip_id AS VARCHAR) FROM {t.name('trips')} "
        f"WHERE CAST(shape_id AS VARCHAR) IN (SELECT id FROM {shapes})"
        if "shape_id" in t.columns("trips")
        else ""
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE _cs_chain_reach AS
        SELECT id FROM {trips}
        UNION SELECT CAST(trip_id AS VARCHAR) FROM {t.name('stop_times')}
              WHERE CAST(stop_id AS VARCHAR) IN (SELECT id FROM {stops})
        {on_shape}
        """
    )
    return "SELECT id FROM _cs_chain_reach"


def _chain_lines(
    t: _Tables, before: Set[str], reach: Optional[str], derived: Optional[Derived]
) -> None:
    """Redraw the stop-chain lines of the trips ``reach`` lists, and drop
    those of ``before`` no trip uses any more."""
    if reach is None or not t.has("shape_lines"):
        return
    con = t.con
    now = {
        str(r[0])
        for r in con.execute(
            f"SELECT DISTINCT shape_id FROM ({_chains(t, reach)})"
        ).fetchall()
    }
    gone = before - now
    if gone:
        # Still used by a trip the change did not reach?
        still = {
            str(r[0])
            for r in con.execute(
                f"SELECT DISTINCT shape_id FROM ({_chains(t, None)}) "
                f"WHERE shape_id IN (SELECT id FROM {_id_table(con, '_cs_gone', gone)})"
            ).fetchall()
        }
        gone -= still
    redraw = now | gone
    if not redraw:
        return
    ids = _id_table(con, "_cs_chain_ids", redraw)
    con.execute(
        f"DELETE FROM {t.name('shape_lines')} "
        f"WHERE CAST(shape_id AS VARCHAR) IN (SELECT id FROM {ids})"
    )
    if not now:
        return
    stop_cols = set(t.columns("stops"))
    if not {"stop_lon", "stop_lat"} <= stop_cols:
        return
    lon, lat, station = "s.stop_lon", "s.stop_lat", ""
    if "parent_station" in stop_cols:
        lon, lat = (
            "coalesce(s.stop_lon, p.stop_lon)",
            "coalesce(s.stop_lat, p.stop_lat)",
        )
        station = f"LEFT JOIN {t.name('stops')} p ON p.stop_id = s.parent_station"
    _insert_lines(
        t,
        f"""
        WITH c AS ({_chains(t, reach)}),
        one AS (SELECT shape_id, min(trip_id) AS trip_id FROM c GROUP BY shape_id),
        pts AS (
            SELECT one.shape_id, st.stop_sequence, {lon} AS lon, {lat} AS lat
            FROM one JOIN {t.name('stop_times')} st ON st.trip_id = one.trip_id
            JOIN {t.name('stops')} s ON s.stop_id = st.stop_id {station}
            WHERE st.stop_sequence IS NOT NULL
        )
        SELECT shape_id, ST_MakeLine(list(ST_Point(lon, lat) ORDER BY stop_sequence))
                   AS geometry
        FROM pts WHERE lon IS NOT NULL AND lat IS NOT NULL
        GROUP BY shape_id HAVING count(*) >= 2
        """,
        derived,
    )


# --------------------------------------------------------------------------


def apply_changeset(
    con: Any,
    tables: Mapping[str, str],
    changeset: ChangeSet,
    derived: Optional[Derived] = None,
) -> Applied:
    """Apply ``changeset`` to ``tables`` (role → table), in the caller's
    transaction. Raises ``ChangeSetError`` for a malformed change set and
    ``ChangeSetIntegrityError`` when it would bring an ERROR; the caller rolls back
    on either."""
    t = _Tables(con, tables)
    net = _squash(_parse_ops(t, changeset))
    touched = _Touched({role: set(rows) for role, rows in net.items() if rows})

    before = _check(t, touched)
    reach = _chain_trips(t, touched)
    chains_before = (
        {
            str(r[0])
            for r in con.execute(
                f"SELECT DISTINCT shape_id FROM ({_chains(t, reach)})"
            ).fetchall()
        }
        if reach is not None
        else set()
    )

    applied = Applied()
    for role, rows in net.items():
        if not rows:
            continue
        counts = {"inserted": 0, "updated": 0, "deleted": 0}
        for key, n in rows.items():
            exists = _exists(t, role, key)
            where = f"{role} {dict(zip(ROLE_KEYS[role], (_jsonable(k) for k in key)))}"
            if n.kind == "insert" and exists:
                raise ChangeSetError(f"{where} already exists")
            if n.kind in ("update", "delete", "replace") and not exists:
                raise ChangeSetError(f"{where} is not there")
        # Deletes first, then updates, then inserts: a replace is a delete
        # and an insert, never an update of a row just inserted.
        for key, n in rows.items():
            if n.kind in ("delete", "replace"):
                _delete(t, role, key)
                counts["deleted" if n.kind == "delete" else "updated"] += 1
        for key, n in rows.items():
            if n.kind == "update":
                _update(t, role, key, n.values, derived)
                counts["updated"] += 1
        for key, n in rows.items():
            if n.kind in ("insert", "replace"):
                _insert(t, role, key, n.values, derived)
                if n.kind == "insert":
                    counts["inserted"] += 1
        applied.rows[role] = counts

    _real_lines(t, touched.ids("shapes", "shape_id"), derived)
    _chain_lines(t, chains_before, reach, derived)

    after = _check(t, touched)
    new = sorted(after - before, key=lambda n: (n.severity, n.code, n.role, str(n.key)))
    errors = [n for n in new if n.severity == "ERROR"]
    if errors:
        raise ChangeSetIntegrityError(errors)
    applied.warnings = [n for n in new if n.severity == "WARNING"]
    _drop_scratch(con)
    return applied


def _drop_scratch(con: Any) -> None:
    """Drop the temp tables the checks used. On a failure the caller's
    rollback drops them; on success they would stay on its connection."""
    for (name,) in con.execute(
        "SELECT table_name FROM duckdb_tables() "
        "WHERE temporary AND starts_with(table_name, '_cs_')"
    ).fetchall():
        con.execute(f"DROP TABLE IF EXISTS {_ident(name)}")
