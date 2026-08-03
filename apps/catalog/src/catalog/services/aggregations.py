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


def facet_aggregations(store: CatalogStore) -> dict[str, str]:
    """``{aggregation name: column expression}`` for the loaded table."""
    return {
        f"{q.facet_name}{_COUNT_SUFFIX}": q.expr
        for q in store.registry.facets().values()
    }


def aggregation_names(store: CatalogStore) -> list[str]:
    """Discovery/execution order: ``total_count`` first, then the facets."""
    return [TOTAL_COUNT, *facet_aggregations(store)]


def available_aggregations(store: CatalogStore) -> dict[str, Any]:
    """The ``/aggregations`` discovery document."""
    aggregations: list[dict[str, Any]] = [{"name": TOTAL_COUNT, "data_type": "integer"}]
    for name in facet_aggregations(store):
        aggregations.append(
            {
                "name": name,
                "data_type": "frequency_distribution",
                "frequency_distribution_data_type": "string",
            }
        )
    return {"aggregations": aggregations}


def run_aggregations(
    store: CatalogStore, p: SearchParams, names: list[str] | None
) -> dict[str, Any]:
    """Execute the requested aggregations; returns an ``AggregationCollection``.

    ``names=None`` runs all known aggregations (``total_count`` + every
    facet). An unknown name anywhere in an explicit list is a 400 naming it,
    before any query runs.
    """
    facets = facet_aggregations(store)
    known = [TOTAL_COUNT, *facets]
    if names is None:
        requested = known
    else:
        for name in names:
            if name not in known:
                raise ApiError(400, f"unknown aggregation name: {name!r}")
        requested = names

    where_sql, params = build_filters(p, registry=store.registry)

    result: list[dict[str, Any]] = []
    for name in requested:
        if name == TOTAL_COUNT:
            rows = safe_query(
                store,
                f"SELECT count(*) FROM {CatalogStore.ITEMS} WHERE {where_sql}",
                params,
            )
            value = int(rows[0][0]) if rows else 0
            result.append({"name": TOTAL_COUNT, "data_type": "integer", "value": value})
            continue

        column = facets[name]
        rows = safe_query(
            store,
            f"""
            SELECT {column} AS key, count(*) AS frequency
            FROM {CatalogStore.ITEMS}
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
            }
        )

    return {"type": "AggregationCollection", "aggregations": result}
