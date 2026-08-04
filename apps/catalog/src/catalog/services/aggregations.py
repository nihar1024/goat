"""STAC Aggregation extension (v0.3.0) support: facet counts for the UI sidebar.

``run_aggregations`` reuses ``catalog.services.search.build_filters`` so every
bucket count is computed under the exact same predicates as the matching
Item Search call (``q`` terms, ``bbox``, ``datetime``, ``cql``, GOAT facet
params, ...) -- and it runs against the items relation, so collections never contribute to a
facet count.

Which facets exist is derived, not fixed: the offered aggregations are the
facetable entries of ``catalog.services.registry`` (built from the loaded
table), each named ``<column>_count``. A facet whose column is absent from the
current file is simply not offered, so a harvester schema change drops the
facet instead of producing SQL against a column that no longer exists.

Facet names are not 1:1 with the query parameter that narrows them (the
``category`` column is filtered via ``?themes=``); the registry holds both
names.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from catalog.errors import ApiError
from catalog.services.search import SearchParams, build_filters, safe_query
from catalog.store import CatalogStore

TOTAL_COUNT = "total_count"


class AggregationBucket(BaseModel):
    """One bucket of a frequency distribution."""

    key: str | None
    data_type: str = "string"
    frequency: int


class Aggregation(BaseModel):
    """One aggregation, in discovery (no value) or executed (with one) form."""

    model_config = ConfigDict(extra="allow")

    name: str
    data_type: str
    frequency_distribution_data_type: str | None = None
    value: int | None = None
    buckets: list[AggregationBucket] | None = None
    #: GOAT extension: the search parameter that narrows this facet, so a
    #: client can build a filter sidebar from discovery instead of hardcoding
    #: a facet-name-to-parameter map (they differ: `category_count` filters
    #: with `?themes=`).
    goat_filter_param: str | None = Field(default=None, alias="goat:filter_param")


class AggregationsDiscovery(BaseModel):
    """``GET /aggregations``: which aggregations this catalog offers."""

    aggregations: list[Aggregation] = Field(default_factory=list)


class AggregationCollection(BaseModel):
    """``GET /aggregate``: the executed aggregations."""

    type: Literal["AggregationCollection"] = "AggregationCollection"
    aggregations: list[Aggregation] = Field(default_factory=list)


#: Suffix that turns a facetable column into its aggregation name, as the
#: Aggregation extension's examples do (``platform`` -> ``platform_count``).
_COUNT_SUFFIX = "_count"


#: What one row of an aggregation counts.
#:
#: ``items`` counts layers, ``collections`` counts datasets. The distinction is
#: not cosmetic: the catalog holds 10,793 layers in 3,834 datasets, so a facet
#: counted over items told a page that lists datasets "8,166 bundles" when
#: selecting that bucket returns 1,207 -- the count and the result set were in
#: different units.
AggregationUnit = Literal["items", "collections"]


def facet_aggregations(
    store: CatalogStore, unit: AggregationUnit = "items"
) -> dict[str, str]:
    """``{aggregation name: column expression}`` for the loaded table.

    Counting datasets keeps every facet the item registry offers, not just the
    ones a collection row happens to carry: ``geometry_type`` lives on layers,
    and "how many datasets have a polygon layer" is a question worth answering.
    Those become semi-joins in :func:`run_aggregations`.
    """
    facets = {
        f"{q.facet_name}{_COUNT_SUFFIX}": q.expr
        for q in store.registry.facets().values()
    }
    if unit == "items":
        return facets
    # Collection-level expressions win where both relations define the facet:
    # `license` is on the collection, so counting it needs no subquery.
    return {
        **facets,
        **{
            f"{q.facet_name}{_COUNT_SUFFIX}": q.expr
            for q in store.collection_registry.facets().values()
        },
    }


def facet_params(store: CatalogStore) -> dict[str, str]:
    """``{aggregation name: the query parameter that narrows it}``.

    Published so a client can build a whole facet sidebar from discovery
    alone. Stripping ``_count`` off the name is *not* enough and quietly
    breaks: ``category_count`` is narrowed with ``?themes=``, and
    ``language_count`` with ``?language=`` over a ``language_code`` column.
    Without this, every consumer hardcodes that map and drifts from the
    server the first time a facet is added.
    """
    return {
        f"{q.facet_name}{_COUNT_SUFFIX}": q.param
        for q in store.registry.facets().values()
    }


def aggregation_names(store: CatalogStore) -> list[str]:
    """Discovery/execution order: ``total_count`` first, then the facets."""
    return [TOTAL_COUNT, *facet_aggregations(store)]


def available_aggregations(
    store: CatalogStore, unit: AggregationUnit = "items"
) -> dict[str, Any]:
    """The ``/aggregations`` discovery document.

    ``unit`` is echoed through so a client discovering facets for a dataset list
    is offered the same set it can then count -- including the item-level facets
    that become semi-joins.
    """
    aggregations: list[dict[str, Any]] = [{"name": TOTAL_COUNT, "data_type": "integer"}]
    params = facet_params(store)
    for name in facet_aggregations(store, unit):
        aggregations.append(
            {
                "name": name,
                "data_type": "frequency_distribution",
                "frequency_distribution_data_type": "string",
                # GOAT extension: the search parameter that narrows this
                # facet. Not in the Aggregation extension, which describes
                # what can be counted but not how to filter by it.
                "goat:filter_param": params[name],
            }
        )
    return {"aggregations": aggregations}


def run_aggregations(
    store: CatalogStore,
    p: SearchParams,
    names: list[str] | None,
    unit: AggregationUnit = "items",
) -> dict[str, Any]:
    """Execute the requested aggregations; returns an ``AggregationCollection``.

    ``names=None`` runs all known aggregations (``total_count`` + every
    facet). An unknown name anywhere in an explicit list is a 400 naming it,
    before any query runs.

    ``unit`` decides what a count counts -- see :data:`AggregationUnit`. A client
    listing datasets must ask for ``collections``, or its facet counts describe a
    different set of things than its results do.
    """
    facets = facet_aggregations(store, unit)
    known = [TOTAL_COUNT, *facets]
    if names is None:
        requested = known
    else:
        for name in names:
            if name not in known:
                raise ApiError(400, f"unknown aggregation name: {name!r}")
        requested = names

    if unit == "collections":
        relation = CatalogStore.COLLECTIONS
        where_sql, params = build_filters(
            p,
            registry=store.collection_registry,
            relation="collections",
            item_registry=store.registry,
        )
        collection_facets = {
            f"{q.facet_name}{_COUNT_SUFFIX}"
            for q in store.collection_registry.facets().values()
        }
    else:
        relation = CatalogStore.ITEMS
        where_sql, params = build_filters(p, registry=store.registry)
        collection_facets = set()

    result: list[dict[str, Any]] = []
    for name in requested:
        if name == TOTAL_COUNT:
            rows = safe_query(
                store,
                f"SELECT count(*) FROM {relation} WHERE {where_sql}",
                params,
            )
            value = int(rows[0][0]) if rows else 0
            result.append({"name": TOTAL_COUNT, "data_type": "integer", "value": value})
            continue

        column = facets[name]
        if unit == "collections" and name not in collection_facets:
            # An item-level facet counted in datasets: group the layers by their
            # value and count DISTINCT collections, so a bundle with four polygon
            # layers counts once. `count(*)` here is what reported 8,166 bundles
            # for 1,207 datasets.
            rows = safe_query(
                store,
                f"""
                SELECT {column} AS key, count(DISTINCT {CatalogStore.ITEMS}.collection) AS frequency
                FROM {CatalogStore.ITEMS}
                WHERE {column} IS NOT NULL AND EXISTS (
                    SELECT 1 FROM {CatalogStore.COLLECTIONS}
                    WHERE {CatalogStore.COLLECTIONS}.id = {CatalogStore.ITEMS}.collection
                      AND {where_sql}
                )
                GROUP BY {column}
                ORDER BY frequency DESC, key ASC
                """,
                params,
            )
            buckets = [
                {"key": key, "data_type": "string", "frequency": int(frequency)}
                for key, frequency in rows
            ]
            result.append(
                {
                    "name": name,
                    "data_type": "frequency_distribution",
                    "frequency_distribution_data_type": "string",
                    "buckets": buckets,
                }
            )
            continue

        rows = safe_query(
            store,
            f"""
            SELECT {column} AS key, count(*) AS frequency
            FROM {relation}
            WHERE {where_sql} AND {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY frequency DESC, key ASC
            """,
            params,
        )
        buckets = [
            {"key": key, "data_type": "string", "frequency": int(frequency)}
            for key, frequency in rows
        ]
        result.append(
            {
                "name": name,
                "data_type": "frequency_distribution",
                "buckets": buckets,
                "goat:filter_param": facet_params(store)[name],
            }
        )

    return {"type": "AggregationCollection", "aggregations": result}
