"""Item Search compliance tests: the six core STAC params + GOAT rules.

Audited against the official spec (see docs/goat-catalog-api.md §2.1) --
these behaviors are non-negotiable: bbox/intersects mutual exclusion,
RFC 3339 datetime parsing (never silently dropped), a pure ``bbox``
intersection unless ``bbox_mode == "relevant"``, collection rows never
leaking into item search, and the sortby whitelist.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from catalog.config import CatalogSettings
from catalog.errors import ApiError
from catalog.services.search import (
    SearchParams,
    build_filters,
    get_collection_row,
    parse_datetime_interval,
    resolve_id,
    safe_query,
    search_items,
)
from catalog.store import CatalogStore
from tests.fixtures.gen_catalog import Row, write_catalog, write_nuts


def test_ids_filter(store: CatalogStore) -> None:
    docs, n = search_items(store, SearchParams(ids=["radverkehrsnetz-dresden-0"]))
    assert n == 1 and docs[0]["id"] == "radverkehrsnetz-dresden-0"


def test_intersects_geojson(store: CatalogStore) -> None:
    poly = {
        "type": "Polygon",
        "coordinates": [[[5, 47], [16, 47], [16, 56], [5, 56], [5, 47]]],
    }
    _, n = search_items(store, SearchParams(intersects=poly))
    assert n > 0


def test_bbox_and_intersects_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        search_items(
            store,
            SearchParams(
                bbox=[5, 47, 16, 56],
                intersects={"type": "Point", "coordinates": [8, 50]},
            ),
        )
    assert e.value.status_code == 400


def test_datetime_rfc3339_timezone(store: CatalogStore) -> None:
    _, n = search_items(store, SearchParams(datetime="2026-01-01T00:00:00Z/.."))
    assert n > 0  # branch parser silently dropped this -- must work now


def test_datetime_garbage_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError):
        search_items(store, SearchParams(datetime="not-a-date"))


def test_datetime_open_end_interval(store: CatalogStore) -> None:
    _, n = search_items(store, SearchParams(datetime="../2026-01-05T00:00:00Z"))
    assert n > 0


def test_datetime_closed_interval(store: CatalogStore) -> None:
    _, n = search_items(
        store,
        SearchParams(datetime="2026-01-01T00:00:00Z/2026-12-31T00:00:00Z"),
    )
    assert n > 0


def test_datetime_both_sides_open_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        search_items(store, SearchParams(datetime="../.."))
    assert e.value.status_code == 400


def test_datetime_empty_side_means_open(store: CatalogStore) -> None:
    """An empty interval side is an open side, exactly like ``..``.

    RFC 3339 / STAC allow both spellings and real clients send both, so
    ``2026-01-01T00:00:00Z/`` must page results, not 400.
    """
    _, n = search_items(store, SearchParams(datetime="2026-01-01T00:00:00Z/"))
    assert n > 0
    _, m = search_items(store, SearchParams(datetime="/2026-12-31T00:00:00Z"))
    assert m > 0


def test_parse_datetime_interval_instant() -> None:
    start, end = parse_datetime_interval("2026-01-01T00:00:00Z")
    assert start == end == datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestRfc3339Grammar:
    """The exact values stac-api-validator probes ``datetime`` with.

    ``datetime.fromisoformat`` alone passes several of the invalid ones (a
    bare date, a timestamp with no offset, ``+0100``), which would silently
    reinterpret the caller's filter, so the parser gates on an RFC 3339
    grammar first.
    """

    @pytest.mark.parametrize(
        "value",
        [
            "1985-04-12T23:20:50.52Z",
            "1985-04-12t23:20:50.000z",  # RFC 3339 allows lowercase t/z
            "1937-01-01T12:00:27.87+01:00",
            "1985-04-12T23:20:50.52Z/..",
            "../1985-04-12T23:20:50.52Z",
            "1985-04-12T23:20:50.52Z/",  # empty side == open side
            "/1985-04-12T23:20:50.52Z",
        ],
    )
    def test_valid(self, value: str) -> None:
        assert parse_datetime_interval(value) != (None, None)

    @pytest.mark.parametrize(
        "value",
        [
            "1985-04-12",  # date only, no time
            "1937-01-01T12:00:27.87+0100",  # offset missing its colon
            "1985-12-12T23:20:50.52",  # no offset at all
            "1985-04-12T23:20:50.Z",  # empty fractional part
            "1985-04-12T23:20:50,52Z",  # comma decimal separator
            "1985-04-12T23:20:50,Z",
            "1986-04-12T23:20:50.52Z/1985-04-12T23:20:50.52Z",  # reversed
            "../..",
            "/",
            "not-a-date",
        ],
    )
    def test_invalid_is_400(self, value: str) -> None:
        with pytest.raises(ApiError) as e:
            parse_datetime_interval(value)
        assert e.value.status_code == 400

    def test_lowercase_t_and_z_parse_to_utc(self) -> None:
        start, end = parse_datetime_interval("1985-04-12t23:20:50.000z")
        assert start == end == datetime(1985, 4, 12, 23, 20, 50, tzinfo=timezone.utc)


def test_bbox_pure_intersection_keeps_sliver(store: CatalogStore) -> None:
    """A bbox that only grazes a tiny edge sliver of a feature must still
    match under the default (pure ST_Intersects) mode -- but must be
    excluded once bbox_mode='relevant' opts into the 30%-area heuristic."""
    xmin, ymin, xmax, ymax = store.query(
        f"SELECT ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), "
        f"ST_YMax(geometry) FROM {store.ITEMS} WHERE id = ?",
        ["radverkehrsnetz-dresden-0"],
    )[0]
    sliver = [xmin - 10.0, ymin - 10.0, xmin + 0.0001, ymax + 10.0]

    docs, n = search_items(
        store, SearchParams(ids=["radverkehrsnetz-dresden-0"], bbox=sliver)
    )
    assert n == 1
    assert docs[0]["id"] == "radverkehrsnetz-dresden-0"

    _, n_relevant = search_items(
        store,
        SearchParams(
            ids=["radverkehrsnetz-dresden-0"], bbox=sliver, bbox_mode="relevant"
        ),
    )
    assert n_relevant == 0


def test_bbox_relevant_keeps_a_fully_contained_feature(store: CatalogStore) -> None:
    """The 30% heuristic drops slivers; it must not drop everything.

    A companion to the sliver test above, which asserts a *zero* result and
    so cannot tell "correctly excluded" from "the branch is broken".
    """
    xmin, ymin, xmax, ymax = store.query(
        f"SELECT ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), "
        f"ST_YMax(geometry) FROM {store.ITEMS} WHERE id = ?",
        ["radverkehrsnetz-dresden-0"],
    )[0]
    # A box that fully contains the feature: the area ratio is 1.0, so every
    # mode must return it.
    containing = [xmin - 1.0, ymin - 1.0, xmax + 1.0, ymax + 1.0]

    for mode in ("strict", "relevant"):
        _, n = search_items(
            store,
            SearchParams(
                ids=["radverkehrsnetz-dresden-0"], bbox=containing, bbox_mode=mode
            ),
        )
        assert n == 1, f"bbox_mode={mode!r} lost a fully contained feature"


def test_bbox_relevant_binds_the_box_in_placeholder_order(
    store: CatalogStore,
) -> None:
    """Placeholders and parameters must line up 1:1, in order.

    The regression guard for a real desync: `bbox_mode=relevant` built its
    envelope pre-filter *inline in the f-string*, so its four values were
    bound after the three `ST_MakeEnvelope` fragments while its `?`s came
    first -- the box arrived as (w, s, e, n) against placeholders ordered
    (w, e, s, n) and the filter compiled to `xmin <= ymin`.

    Asserted on the compiled SQL rather than on results, because whether a
    swapped box changes the answer depends on the data: with German
    coordinates (lon ~13, lat ~51) the mangled predicate still happens to
    hold, and every fixture-based assertion passes while the branch is
    wrong. `?bbox=100,10,110,20` is where it shows.
    """
    where_sql, params = build_filters(
        SearchParams(bbox=[10.0, 40.0, 20.0, 50.0], bbox_mode="relevant"),
        registry=store.registry,
    )
    assert where_sql.count("?") == len(params)
    # The envelope pre-filter comes first in the SQL, so its (w, e, s, n)
    # must be the first four parameters.
    assert params[:4] == [10.0, 20.0, 40.0, 50.0]


def test_bbox_invalid_count_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        search_items(store, SearchParams(bbox=[5, 47, 16]))
    assert e.value.status_code == 400


def test_bbox_six_numbers_ignores_elevation(store: CatalogStore) -> None:
    docs4, n4 = search_items(store, SearchParams(bbox=[5, 47, 16, 56]))
    docs6, n6 = search_items(store, SearchParams(bbox=[5, 47, 0, 16, 56, 1000]))
    assert n4 == n6
    assert {d["id"] for d in docs4} == {d["id"] for d in docs6}


def test_sortby_title_asc(store: CatalogStore) -> None:
    docs, n = search_items(
        store, SearchParams(sortby=[("properties.title", "asc")], limit=50)
    )
    assert n > 0
    titles = [d["title"] for d in docs]
    assert titles == sorted(titles)


def test_sortby_unknown_field_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        search_items(store, SearchParams(sortby=[("properties.nope", "asc")]))
    assert e.value.status_code == 400


def test_default_sort_is_updated_desc(store: CatalogStore) -> None:
    # The document's own `properties.updated` is sparse by design (real
    # harvester items omit it on roughly half of rows -- see
    # tests/fixtures/gen_catalog.py), so sort order is checked against the
    # underlying `updated` column (always populated) rather than the
    # embedded JSON field.
    docs, _ = search_items(store, SearchParams(limit=50))
    ids = [d["id"] for d in docs]
    placeholders = ", ".join("?" for _ in ids)
    rows = store.query(
        f"SELECT id, updated FROM {store.ITEMS} WHERE id IN ({placeholders})", ids
    )
    updated_by_id = dict(rows)
    updated = [updated_by_id[i] for i in ids]
    assert updated == sorted(updated, reverse=True)


def test_pagination_matched_count(store: CatalogStore) -> None:
    docs_all, n_all = search_items(store, SearchParams(limit=1000))
    docs_page, n_page = search_items(store, SearchParams(limit=5, offset=5))
    assert n_page == n_all
    assert len(docs_page) == 5
    assert len(docs_all) == n_all


def test_collection_rows_excluded_from_item_search(store: CatalogStore) -> None:
    docs, n = search_items(store, SearchParams(ids=["src-1"]))
    assert n == 0
    assert docs == []


def test_grouped_one_entry_per_bundle(store: CatalogStore) -> None:
    member_ids = [
        row[0]
        for row in store.query(
            f"SELECT id FROM {store.ITEMS} WHERE collection = 'src-1'"
        )
    ]
    assert len(member_ids) == 4

    newest_id = store.query(
        f"SELECT id FROM {store.ITEMS} WHERE collection = 'src-1' "
        f"ORDER BY updated DESC LIMIT 1"
    )[0][0]

    docs, n = search_items(store, SearchParams(ids=member_ids, grouped=True))
    assert n == 1
    assert len(docs) == 1
    assert docs[0]["id"] == newest_id
    assert docs[0]["member_count"] == 4


def test_grouped_ungrouped_member_count_matches(store: CatalogStore) -> None:
    member_ids = [
        row[0]
        for row in store.query(
            f"SELECT id FROM {store.ITEMS} WHERE collection = 'src-1'"
        )
    ]
    _, n_ungrouped = search_items(store, SearchParams(ids=member_ids))
    assert n_ungrouped == 4


def test_q_free_text_matches_title(store: CatalogStore) -> None:
    _, n = search_items(store, SearchParams(q="Radverkehrsnetz"))
    assert n > 0


def _small_store(tmp_path: Path, n: int = 40) -> CatalogStore:
    """A smaller, still-deterministic (seed 42) catalog than the 200-row
    ``store`` fixture. At this size ``radverkehrsnetz-dresden-0`` is the
    *only* item mentioning "Radverkehrsnetz" (the next occurrence of that
    topic only appears at row 105 in the full fixture) -- verified by
    direct inspection, not assumed -- so relevance-ranking assertions here
    are deterministic instead of resting on a near-tie between two
    same-topic rows (see the module-level report for why the full 200-row
    fixture isn't used for the "ranked first" assertion)."""
    write_catalog(tmp_path, n=n)
    write_nuts(tmp_path)
    s = CatalogStore(CatalogSettings(data_dir=tmp_path))
    s.ensure_current()
    return s


def _desc_only_match_row() -> Row:
    """A row that matches "Radverkehrsnetz" only in its (long) description.

    ``test_q_single_term_ranks_dresden_row_first`` needs a real competitor: a
    query returning exactly one hit cannot distinguish "filters correctly" from
    "ranks correctly", since any ordering of a one-element list is trivially
    "first". Dresden's title literally *is* "Radverkehrsnetz Dresden 2018", so
    the title-hit tier must put it above this description-only mention.
    """
    return Row(
        id="bebauungsplan-berlin-999",
        collection=None,
        type="feature",
        geom_type="polygon",
        title="Bebauungsplan Berlin 2020",
        description=(
            "Der Datensatz enthaelt Geometrien und Sachdaten fuer die "
            "Verwaltung. Zusaetzliche Informationen zum Radverkehrsnetz "
            "sind im Anhang enthalten und werden regelmaessig aktualisiert. "
            "Die Daten stehen als Download sowie ueber Dienste bereit fuer "
            "Analysen in Planung Umwelt Verkehr und Statistik."
        ),
        license="CC-BY-4.0",
        category="transportation",
        language="de",
        publisher="Landesamt 1",
        geometry_wkt="POLYGON((6 48, 6.5 48, 6.5 48.5, 6 48.5, 6 48))",
        geometry_geojson={
            "type": "Polygon",
            "coordinates": [[[6, 48], [6.5, 48], [6.5, 48.5], [6, 48.5], [6, 48]]],
        },
        item_datetime=datetime(2026, 1, 2, tzinfo=timezone.utc),
        created=datetime(2026, 1, 2, tzinfo=timezone.utc),
        updated=datetime(2026, 1, 3, tzinfo=timezone.utc),
        version="v1",
        parquet_url=None,
    )


def test_q_single_term_ranks_dresden_row_first(tmp_path: Path) -> None:
    """A title hit outranks a description-only hit for the same term."""
    competitor = _desc_only_match_row()
    # 40 rows: the size at which `radverkehrsnetz-dresden-0` is the only
    # generated row mentioning "Radverkehrsnetz" (see _small_store), so the
    # ordering assertion rests on the injected competitor rather than on a
    # near-tie between two same-topic rows.
    write_catalog(tmp_path, n=40, extra_rows=[competitor])
    write_nuts(tmp_path)
    small = CatalogStore(CatalogSettings(data_dir=tmp_path))
    small.ensure_current()

    docs, n = search_items(small, SearchParams(q="Radverkehrsnetz"))
    assert n >= 2
    assert competitor.id in {d["id"] for d in docs}
    assert docs[0]["id"] == "radverkehrsnetz-dresden-0"


def test_q_ranks_by_how_completely_a_row_matches(store: CatalogStore) -> None:
    """Multi-word ``q``: rows matching more of the words rank higher.

    This is what replaced BM25 scoring. Recall stays generous -- one word is
    enough to be returned, so an over-specified query never answers empty --
    but the ordering is by number of words matched, then by how many of them
    landed in the title.
    """
    docs, n = search_items(store, SearchParams(q="Grünflächen München", limit=1000))
    assert n > 0

    def matched(doc: dict[str, Any]) -> tuple[int, int]:
        haystack = " ".join(
            str(doc.get(k) or "") for k in ("title", "description")
        ).lower()
        title = str(doc.get("title") or "").lower()
        words = ("grünflächen", "münchen")
        return (
            sum(w in haystack for w in words),
            sum(w in title for w in words),
        )

    ranks = [matched(d) for d in docs]
    assert ranks == sorted(ranks, reverse=True), ranks
    assert ranks[0][0] == 2, "a row matching both words must come first"


def test_q_comma_or_combines_terms(store: CatalogStore) -> None:
    _, n_radverkehr = search_items(store, SearchParams(q="Radverkehrsnetz", limit=1000))
    _, n_gruen = search_items(store, SearchParams(q="Grünflächen", limit=1000))
    _, n_or = search_items(
        store, SearchParams(q="Radverkehrsnetz,Grünflächen", limit=1000)
    )
    assert n_or >= n_radverkehr
    assert n_or >= n_gruen
    # Rules out a degenerate "OR just returns everything" bug: the union
    # can be at most the sum of the two single-term counts.
    assert n_or <= n_radverkehr + n_gruen


def test_q_no_hits_returns_empty_not_error(store: CatalogStore) -> None:
    docs, n = search_items(store, SearchParams(q="zzz-nonexistent-query-term-zzz"))
    assert (docs, n) == ([], 0)


def test_q_blank_terms_treated_as_no_q(store: CatalogStore) -> None:
    """An all-comma/blank q (",", "  ", ",,") must behave like q=None, not
    a 400 or an empty-result filter -- free text has no invalid input."""
    docs_blank, n_blank = search_items(store, SearchParams(q=" , ,  "))
    docs_none, n_none = search_items(store, SearchParams(q=None))
    assert n_blank == n_none
    assert {d["id"] for d in docs_blank} == {d["id"] for d in docs_none}


def test_q_german_stemmer_matches_singular_to_plural(store: CatalogStore) -> None:
    """German stemmer finding: querying the singular 'Grünfläche' DOES match
    the indexed plural 'Grünflächen' -- the compound-noun stemmer here
    handles this case fine, so no relaxation to exact-form matching is
    needed (unlike the brief's fallback allowance)."""
    _, n = search_items(store, SearchParams(q="Grünfläche"))
    assert n > 0


def test_q_composes_with_license_facet_filter(store: CatalogStore) -> None:
    _, n_q_only = search_items(store, SearchParams(q="Radverkehrsnetz", limit=1000))
    docs, n_both = search_items(
        store,
        SearchParams(q="Radverkehrsnetz", fields={"license": "CC-BY-4.0"}, limit=1000),
    )
    assert 0 < n_both < n_q_only
    assert all(d["license"] == "CC-BY-4.0" for d in docs)
    assert "radverkehrsnetz-dresden-0" in {d["id"] for d in docs}


def test_q_no_ranking_injected_with_explicit_sortby(store: CatalogStore) -> None:
    """With an explicit sortby, q must only filter -- no relevance-ranking
    ORDER BY prefix gets injected -- so the result is sorted purely by the
    requested field, not by BM25 score first."""
    docs, n = search_items(
        store,
        SearchParams(
            q="Radverkehrsnetz,Grünflächen",
            sortby=[("properties.title", "asc")],
            limit=1000,
        ),
    )
    assert n > 0
    titles = [d["title"] for d in docs]
    assert titles == sorted(titles)


def test_q_composes_with_bbox_boost_ranking_order(store: CatalogStore) -> None:
    """boost prefix first, then BM25 score DESC: every bbox_boost-matched
    row must precede every non-matched row, even though both groups are
    independently ranked by q relevance."""
    boost_bbox = [8.0, 50.0, 9.0, 51.0]
    intersecting_ids = {
        row[0]
        for row in store.query(
            f"SELECT id FROM {store.ITEMS} "
            f"WHERE ST_Intersects(geometry, ST_MakeEnvelope(?, ?, ?, ?))",
            boost_bbox,
        )
    }
    docs, n = search_items(
        store,
        SearchParams(
            q="Radverkehrsnetz,Grünflächen", bbox_boost=boost_bbox, limit=1000
        ),
    )
    assert n > 0
    flags = [d["id"] in intersecting_ids for d in docs]
    assert flags == sorted(flags, reverse=True)


def test_q_grouped_still_filters_but_skips_ranking(store: CatalogStore) -> None:
    """grouped=True: q still filters members on the WHERE side (members not
    matching q must not leak a bundle in), but ranking falls back to the
    default group ordering (updated DESC) rather than injecting per-member
    BM25 into ORDER BY -- documented simplification, see report."""
    docs, n = search_items(
        store, SearchParams(q="Radverkehrsnetz", grouped=True, limit=1000)
    )
    assert n > 0
    # As in test_default_sort_is_updated_desc: `properties.updated` is
    # sparse by design, so check the always-populated `updated` column
    # instead of the embedded JSON field.
    ids = [d["id"] for d in docs]
    placeholders = ", ".join("?" for _ in ids)
    rows = store.query(
        f"SELECT id, updated FROM {store.ITEMS} WHERE id IN ({placeholders})", ids
    )
    updated_by_id = dict(rows)
    updated = [updated_by_id[i] for i in ids]
    assert updated == sorted(updated, reverse=True)


def test_bbox_mutually_exclusive_via_build_filters(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        build_filters(
            SearchParams(
                bbox=[5, 47, 16, 56],
                intersects={"type": "Point", "coordinates": [8, 50]},
            ),
            registry=store.registry,
        )
    assert e.value.status_code == 400


def test_build_filters_invalid_bbox_mode(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        build_filters(SearchParams(bbox_mode="bogus"), registry=store.registry)
    assert e.value.status_code == 400


def test_unknown_filter_parameter_is_400(store: CatalogStore) -> None:
    """An unrecognised scalar filter names what is available rather than
    matching nothing."""
    with pytest.raises(ApiError) as e:
        build_filters(
            SearchParams(fields={"licence": "CC-BY-4.0"}), registry=store.registry
        )
    assert e.value.status_code == 400
    assert "licence" in e.value.detail
    assert "license" in e.value.detail


def test_scalar_filter_values_are_typed(store: CatalogStore) -> None:
    """`year` is an integer queryable, so its values are compared as integers
    and a non-numeric value is a 400 rather than a DuckDB error."""
    _, n = search_items(store, SearchParams(fields={"year": "2026"}, limit=1000))
    assert n > 0
    with pytest.raises(ApiError) as e:
        search_items(store, SearchParams(fields={"year": "not-a-year"}))
    assert e.value.status_code == 400


def test_get_document_found(store: CatalogStore) -> None:
    # Collections live in their own relation, so an *item* id is not found here.
    assert get_collection_row(store, "radverkehrsnetz-dresden-0") is None
    row = get_collection_row(store, "src-1")
    assert row is not None and row["id"] == "src-1"


def test_get_document_missing(store: CatalogStore) -> None:
    assert get_collection_row(store, "does-not-exist") is None


def test_resolve_id_item(store: CatalogStore) -> None:
    result = resolve_id(store, "radverkehrsnetz-dresden-0")
    assert result is not None
    assert result["kind"] == "item"
    assert result["row"]["id"] == "radverkehrsnetz-dresden-0"
    assert result["collection_id"] is None


def test_resolve_id_collection(store: CatalogStore) -> None:
    result = resolve_id(store, "src-1")
    assert result is not None
    assert result["kind"] == "collection"
    assert result["collection_row"]["id"] == "src-1"
    assert len(result["member_rows"]) == 4


def test_resolve_id_missing(store: CatalogStore) -> None:
    assert resolve_id(store, "does-not-exist") is None


def test_resolve_id_member_fanout_is_capped(
    store: CatalogStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I4 regression: `resolve_id`'s member fetch must be capped
    (`_MEMBER_LIMIT`), while `member_count` still reports the TRUE
    (uncapped) total -- so a caller can tell "truncated" apart from "this
    bundle really only has N members". Monkeypatches the limit down to 2
    (rather than crafting a >100-member fixture) against the fixture's
    real 4-member `src-1` bundle.
    """
    import catalog.services.search as search_module

    monkeypatch.setattr(search_module, "_MEMBER_LIMIT", 2)

    result = resolve_id(store, "src-1")
    assert result is not None
    assert result["kind"] == "collection"
    assert result["member_count"] == 4
    assert len(result["member_rows"]) == 2


def test_resolve_id_member_count_matches_when_under_limit(
    store: CatalogStore,
) -> None:
    result = resolve_id(store, "src-1")
    assert result is not None
    assert result["member_count"] == 4
    assert len(result["member_rows"]) == 4


def test_bbox_boost_ranks_intersecting_first(store: CatalogStore) -> None:
    """bbox_boost ranks matches first WITHOUT excluding non-matches: same
    numberMatched with and without the boost, and every boosted-in row comes
    before every non-intersecting row in the returned order."""
    boost_bbox = [8.0, 50.0, 9.0, 51.0]
    intersecting_ids = {
        row[0]
        for row in store.query(
            f"SELECT id FROM {store.ITEMS} "
            f"WHERE ST_Intersects(geometry, ST_MakeEnvelope(?, ?, ?, ?))",
            boost_bbox,
        )
    }
    # Sanity on the fixture: the box must split the item set, or this test
    # would pass vacuously.
    assert 0 < len(intersecting_ids) < 199

    _, n_plain = search_items(store, SearchParams(limit=1000))
    docs_boosted, n_boosted = search_items(
        store, SearchParams(limit=1000, bbox_boost=boost_bbox)
    )
    assert n_boosted == n_plain

    flags = [d["id"] in intersecting_ids for d in docs_boosted]
    assert any(flags)
    assert not all(flags)
    assert flags == sorted(flags, reverse=True)  # all True's before all False's


def test_bbox_boost_combines_with_grouped(store: CatalogStore) -> None:
    boost_bbox = [8.0, 50.0, 9.0, 51.0]
    _, n_plain = search_items(store, SearchParams(grouped=True, limit=1000))
    _, n_boosted = search_items(
        store, SearchParams(grouped=True, limit=1000, bbox_boost=boost_bbox)
    )
    assert n_boosted == n_plain


def test_bbox_boost_invalid_count_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as e:
        search_items(store, SearchParams(bbox_boost=[5, 47, 16]))
    assert e.value.status_code == 400


def test_out_of_memory_is_503_not_400(store: CatalogStore) -> None:
    """A query the server cannot afford is not the caller's mistake.

    Both come back through the same DuckDB error channel, so without this split
    a memory-limited pod reports 4xx -- pointing an operator at client requests
    instead of at the limit that actually caused it.
    """
    import duckdb as _duckdb

    def raise_oom(sql: str, params: list[Any] | None = None) -> list[Any]:
        raise _duckdb.OutOfMemoryException("failed to allocate data of size 128 MiB")

    original = store.query
    try:
        store.query = raise_oom  # type: ignore[method-assign]
        with pytest.raises(ApiError) as exc:
            safe_query(store, "SELECT 1")
    finally:
        store.query = original  # type: ignore[method-assign]
    assert exc.value.status_code == 503
    assert "out of memory" in exc.value.detail


def test_invalid_query_is_still_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as exc:
        safe_query(store, "SELECT nonexistent_column FROM cat")
    assert exc.value.status_code == 400
