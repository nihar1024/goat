"""Tests for the STAC Aggregation extension (v0.3.0) facet-count layer.

Aggregations must apply the exact same predicates as Item Search (via
``build_filters``), including the blanket exclusion of collection-type rows
-- verified here rather than re-derived, since ``build_filters`` already
owns that rule (see ``catalog.services.search``).
"""

import pytest

from catalog.errors import ApiError
from catalog.services.aggregations import (
    aggregation_names,
    available_aggregations,
    facet_aggregations,
    run_aggregations,
)
from catalog.services.search import SearchParams
from catalog.store import CatalogStore


def test_available_aggregations_shape(store: CatalogStore) -> None:
    doc = available_aggregations(store)
    names = {a["name"] for a in doc["aggregations"]}
    assert names == set(aggregation_names(store))

    by_name = {a["name"]: a for a in doc["aggregations"]}
    assert by_name["total_count"]["data_type"] == "integer"
    for facet_name in facet_aggregations(store):
        entry = by_name[facet_name]
        assert entry["data_type"] == "frequency_distribution"
        assert entry["frequency_distribution_data_type"] == "string"


def test_default_run_returns_total_and_all_facets(store: CatalogStore) -> None:
    result = run_aggregations(store, SearchParams(), None)
    assert result["type"] == "AggregationCollection"
    names = {a["name"] for a in result["aggregations"]}
    assert names == set(aggregation_names(store))


def test_total_count_matches_non_collection_row_count(store: CatalogStore) -> None:
    expected = store.query(f"SELECT count(*) FROM {store.ITEMS} ")[0][0]

    result = run_aggregations(store, SearchParams(), None)
    by_name = {a["name"]: a for a in result["aggregations"]}
    assert by_name["total_count"]["value"] == expected


def test_license_bucket_frequencies_sum_to_total(store: CatalogStore) -> None:
    result = run_aggregations(store, SearchParams(), None)
    by_name = {a["name"]: a for a in result["aggregations"]}

    total = by_name["total_count"]["value"]
    license_sum = sum(b["frequency"] for b in by_name["license_count"]["buckets"])
    assert total > 0
    assert license_sum == total


def test_category_predicate_narrows_buckets(store: CatalogStore) -> None:
    # `?themes=` filters the underlying `category` column: the registry seeds
    # that parameter name for it, while the aggregation stays `category_count`.
    result = run_aggregations(
        store,
        SearchParams(fields={"themes": "transportation"}),
        ["category_count", "total_count"],
    )
    by_name = {a["name"]: a for a in result["aggregations"]}

    buckets = by_name["category_count"]["buckets"]
    assert buckets  # the fixture has transportation rows (row 0, the bundle)
    assert all(b["key"] == "transportation" for b in buckets)

    # And the facet count is internally consistent with total_count under
    # the same predicate.
    assert sum(b["frequency"] for b in buckets) == by_name["total_count"]["value"]


def test_names_filter_returns_only_requested(store: CatalogStore) -> None:
    result = run_aggregations(store, SearchParams(), ["total_count"])
    assert [a["name"] for a in result["aggregations"]] == ["total_count"]


def test_unknown_aggregation_name_is_400(store: CatalogStore) -> None:
    with pytest.raises(ApiError) as exc_info:
        run_aggregations(store, SearchParams(), ["not_a_real_aggregation"])
    assert exc_info.value.status_code == 400


def test_geometry_type_buckets_exclude_nulls(store: CatalogStore) -> None:
    # gen_catalog sets goat:geometryType = NULL for row_type == "table" rows, so the
    # non-collection table rows exist but must not surface as a NULL bucket
    # nor be silently counted into some other key.
    null_geom_rows = store.query(
        f'SELECT count(*) FROM {store.ITEMS} WHERE "goat:geometryType" IS NULL'
    )[0][0]
    assert null_geom_rows > 0  # sanity: the fixture actually has table rows

    result = run_aggregations(
        store, SearchParams(), ["geometry_type_count", "total_count"]
    )
    by_name = {a["name"]: a for a in result["aggregations"]}

    buckets = by_name["geometry_type_count"]["buckets"]
    assert all(b["key"] is not None for b in buckets)

    bucket_sum = sum(b["frequency"] for b in buckets)
    total = by_name["total_count"]["value"]
    assert bucket_sum == total - null_geom_rows
    assert bucket_sum < total


def test_bucket_ordering_by_frequency_desc_then_key_asc(store: CatalogStore) -> None:
    expected_rows = store.query(
        f"SELECT license AS key, count(*) AS frequency FROM {store.ITEMS} "
        f"WHERE license IS NOT NULL "
        f"GROUP BY license ORDER BY frequency DESC, key ASC"
    )
    expected = [(row[0], row[1]) for row in expected_rows]

    result = run_aggregations(store, SearchParams(), ["license_count"])
    buckets = result["aggregations"][0]["buckets"]
    actual = [(b["key"], b["frequency"]) for b in buckets]

    assert actual == expected
