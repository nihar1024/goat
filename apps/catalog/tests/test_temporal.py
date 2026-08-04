"""The ``datetime`` filter against every temporal shape STAC allows.

The shared fixture dates every row as an instant, which is what the harvester
publishes *today* (contract C11: no ``start_datetime``, and 3,834 of 3,834
Collections carry ``extent.temporal.interval == [[null, null]]``). That corpus
cannot tell a correct temporal filter from one that happens to work on instants,
so this module publishes the other shapes deliberately:

* an **instant** -- ``datetime`` only,
* a **range** -- ``datetime: null`` + ``start_datetime``/``end_datetime``, which
  the Item spec requires be spelled exactly that way,
* an **open-ended range** -- a start with no end ("everything since 2020"),
* **undated** -- neither, which is over half the live catalog,

and asserts what a search returns for each. The bug this guards against is not
hypothetical: the mirror used to store one timestamp per row, read from
``extent.temporal.interval[1][1]`` -- the END of the FIRST interval -- so a
dataset covering 2014-2021 was stored as an instant at 2021 and a search for
2015 could not find it.

Written against the real converter (``build_mirror``) and the real store rather
than hand-written SQL, so it fails if either side of the contract moves.
"""

from pathlib import Path
from typing import Any

import duckdb
import pytest
from goatlib.tasks.catalog_mirror import build_mirror

from catalog.config import CatalogSettings
from catalog.services.search import SearchParams, search_collections, search_items
from catalog.store import CatalogStore
from tests.test_mirror_roundtrip import _publish

_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [
        [[10.0, 50.0], [11.0, 50.0], [11.0, 51.0], [10.0, 51.0], [10.0, 50.0]]
    ],
}
_BBOX = [10.0, 50.0, 11.0, 51.0]


def _item(item_id: str, collection: str, temporal: dict[str, Any]) -> dict[str, Any]:
    """A published Item whose ``properties`` carry exactly ``temporal``."""
    return {
        "id": item_id,
        "type": "Feature",
        "stac_version": "1.0.0",
        "collection": collection,
        "bbox": _BBOX,
        "geometry": _GEOMETRY,
        "links": [],
        "assets": {},
        "properties": {
            "title": item_id,
            "description": f"Layer {item_id}",
            # Every shape declares all three members, present-and-null where it
            # has nothing to say: parquet unifies one schema over all rows, so a
            # member only *one* row mentions is a column on all of them. That is
            # also true of the real published file, which is why the converter
            # has to tolerate nulls rather than absent columns.
            "datetime": None,
            "start_datetime": None,
            "end_datetime": None,
            **temporal,
        },
    }


def _collection(
    collection_id: str, interval: list[list[str | None]], title: str
) -> dict[str, Any]:
    return {
        "id": collection_id,
        "type": "Collection",
        "stac_version": "1.0.0",
        "title": title,
        "description": f"Dataset {collection_id}",
        "license": "CC-BY-4.0",
        "extent": {
            "spatial": {"bbox": [_BBOX]},
            "temporal": {"interval": interval},
        },
        "links": [],
    }


#: One dataset per temporal shape, item and Collection agreeing -- which is what
#: STAC asks for: a Collection's temporal extent is the envelope of its items'.
_DATASETS: tuple[tuple[str, list[list[str | None]], dict[str, Any]], ...] = (
    (
        "instant",
        [["2015-06-01T00:00:00Z", "2015-06-01T00:00:00Z"]],
        {"datetime": "2015-06-01T00:00:00Z"},
    ),
    (
        "range",
        [["2014-01-01T00:00:00Z", "2021-12-31T00:00:00Z"]],
        {
            "start_datetime": "2014-01-01T00:00:00Z",
            "end_datetime": "2021-12-31T00:00:00Z",
        },
    ),
    (
        "open_end",
        [["2020-01-01T00:00:00Z", None]],
        {"start_datetime": "2020-01-01T00:00:00Z"},
    ),
    ("undated", [[None, None]], {}),
)


@pytest.fixture()
def temporal_store(tmp_path: Path) -> CatalogStore:
    """A catalog holding one single-layer dataset per temporal shape."""
    items = [
        _item(f"item-{name}", f"src-{name}", temporal)
        for name, _, temporal in _DATASETS
    ]
    collections = [
        _collection(f"src-{name}", interval, name) for name, interval, _ in _DATASETS
    ]

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL json; LOAD json;")
    published_items = tmp_path / "published_items.parquet"
    published_collections = tmp_path / "published_collections.parquet"
    _publish(con, items, published_items, "items_pub", tmp_path)
    _publish(con, collections, published_collections, "colls_pub", tmp_path)
    build_mirror(
        published_items,
        published_collections,
        tmp_path / "mirror_items.parquet",
        tmp_path / "mirror_collections.parquet",
        con,
    )
    con.close()
    (tmp_path / "VERSION").write_text("v-temporal-1")

    store = CatalogStore(CatalogSettings(data_dir=tmp_path))
    store.ensure_current()
    return store


#: The two searches, keyed by the relation they query, so one test body can
#: assert both. `search_collections` is what the catalog page calls (a card is a
#: dataset); `search_items` is what a layer-level client calls.
_SEARCHES = {"items": search_items, "collections": search_collections}


def _found(store: CatalogStore, relation: str, datetime: str | None = None) -> set[str]:
    """The ids one search returns, as a set."""
    rows, matched = _SEARCHES[relation](
        store, SearchParams(datetime=datetime, limit=50)
    )
    # The count drives the UI's "N datasets" and paging, so it has to agree with
    # the page rather than be assumed to.
    assert matched == len(rows)
    return {row["id"] for row in rows}


@pytest.mark.parametrize("relation", ["items", "collections"])
@pytest.mark.parametrize(
    ("interval", "expected", "why"),
    [
        (
            "2015-01-01T00:00:00Z/2015-12-31T00:00:00Z",
            {"instant", "range"},
            "a year inside the range, and the instant that falls in it",
        ),
        (
            "2016-01-01T00:00:00Z/2016-12-31T00:00:00Z",
            {"range"},
            "a year the range covers but no instant names: the regression case",
        ),
        (
            "2025-01-01T00:00:00Z/2025-12-31T00:00:00Z",
            {"open_end"},
            "beyond every closed range, but an open-ended one still runs",
        ),
        (
            "2013-01-01T00:00:00Z/2013-12-31T00:00:00Z",
            set(),
            "before everything: no row overlaps",
        ),
        (
            "../2014-06-01T00:00:00Z",
            {"range"},
            "open lower bound -- only the range had begun by then",
        ),
        (
            "2021-06-01T00:00:00Z/..",
            {"range", "open_end"},
            "open upper bound -- both ranges were still running",
        ),
    ],
)
def test_datetime_selects_every_overlapping_row(
    temporal_store: CatalogStore,
    relation: str,
    interval: str,
    expected: set[str],
    why: str,
) -> None:
    """A row matches when its extent overlaps the query, on either relation.

    Both relations are asserted with the same expectations because a
    single-layer dataset and its layer state the same time: an item's own
    ``datetime``/``start_datetime`` and its Collection's ``extent.temporal``
    describe one thing, so a dataset search and a layer search must agree about
    which datasets exist in a period. Item ids are prefixed, hence the strip.
    """
    found = {
        found_id.removeprefix("item-").removeprefix("src-")
        for found_id in _found(temporal_store, relation, interval)
    }
    assert found == expected, why


@pytest.mark.parametrize("relation", ["items", "collections"])
def test_undated_rows_are_returned_when_nothing_is_asked(
    temporal_store: CatalogStore, relation: str
) -> None:
    """No date filter means no date filter -- undated rows are still results.

    Excluding them from an unfiltered search would hide 52% of the live catalog;
    they are excluded only once a period is named, because a dataset that never
    says when it is from cannot be shown to belong to one.
    """
    assert len(_found(temporal_store, relation)) == len(_DATASETS)


@pytest.mark.parametrize(
    ("year", "expected", "why"),
    [
        ("2014", {"range"}, "the year the range starts in"),
        ("2015", {"instant"}, "the instant's year"),
        ("2016", set(), "inside the range, but not where it starts"),
    ],
)
def test_year_names_where_a_period_starts_not_every_year_it_covers(
    temporal_store: CatalogStore, year: str, expected: set[str], why: str
) -> None:
    """``?year=`` and ``?datetime=`` answer two different questions, on purpose.

    ``year`` is one expression over one column, so it can only name the year a
    row's period *begins*; ``datetime`` compares both bounds and so selects
    everything running through a period -- which is what a client wanting "data
    from 2016" should send, and what the case above asserts. Pinned here because
    the difference shows up only on ranged rows: on the instant-dated rows that
    are most of the catalog the two agree, so a wrong expectation would survive
    unnoticed.
    """
    rows, _ = search_collections(
        temporal_store, SearchParams(fields={"year": year}, limit=50)
    )
    assert {row["id"].removeprefix("src-") for row in rows} == expected, why


def test_the_mirror_stores_the_whole_interval(temporal_store: CatalogStore) -> None:
    """``datetime_start``/``datetime_end`` bound the row, on both relations.

    Asserted on the stored values as well as through search, because the failure
    this file exists for was invisible from the outside: a range collapsed to its
    end point still answers *some* queries correctly.
    """
    for table, prefix in (("items", "item-"), ("collections", "src-")):
        rows = {
            row[0].removeprefix(prefix): (row[1], row[2])
            for row in temporal_store.query(
                f"SELECT id, datetime_start, datetime_end FROM {table}"
            )
        }
        starts = {name: value[0] for name, value in rows.items()}
        ends = {name: value[1] for name, value in rows.items()}

        assert starts["range"] is not None and starts["range"].year == 2014
        assert ends["range"] is not None and ends["range"].year == 2021
        # An instant is a zero-length interval, which is why one predicate
        # serves both shapes.
        assert starts["instant"] == ends["instant"] != None  # noqa: E711
        # Open-ended stays open: a null end is "still running", not "unknown".
        assert starts["open_end"] is not None and ends["open_end"] is None
        assert starts["undated"] is None and ends["undated"] is None


def test_a_multi_interval_extent_spans_all_of_its_intervals(tmp_path: Path) -> None:
    """A Collection may publish several intervals; the extent is their envelope.

    ``extent.temporal.interval`` is a list, and the spec is explicit that the
    first entry is the whole extent while later ones may describe sub-periods.
    Reading a single element -- which the mirror used to do -- gets this wrong in
    both directions, so the envelope is computed over all of them.
    """
    collections = [
        _collection(
            "src-multi",
            [
                ["2000-01-01T00:00:00Z", "2005-12-31T00:00:00Z"],
                ["2010-01-01T00:00:00Z", "2012-12-31T00:00:00Z"],
            ],
            "multi",
        )
    ]
    items = [_item("item-multi", "src-multi", {"datetime": "2000-01-01T00:00:00Z"})]

    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL json; LOAD json;")
    published_items = tmp_path / "published_items.parquet"
    published_collections = tmp_path / "published_collections.parquet"
    _publish(con, items, published_items, "items_pub", tmp_path)
    _publish(con, collections, published_collections, "colls_pub", tmp_path)
    build_mirror(
        published_items,
        published_collections,
        tmp_path / "mirror_items.parquet",
        tmp_path / "mirror_collections.parquet",
        con,
    )
    con.close()
    (tmp_path / "VERSION").write_text("v-temporal-multi")

    store = CatalogStore(CatalogSettings(data_dir=tmp_path))
    store.ensure_current()
    start, end = store.query("SELECT datetime_start, datetime_end FROM collections")[0]
    assert (start.year, end.year) == (2000, 2012)
