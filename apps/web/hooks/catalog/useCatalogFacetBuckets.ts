import useSWR from "swr";

import {
  CATALOG_API_BASE_URL,
  type CatalogSearchParams,
  buildCatalogQuery,
} from "@/lib/api/catalog";
import { fetcher } from "@/lib/api/fetcher";
import type { CatalogAggregationBucket, CatalogAggregations } from "@/lib/validations/catalog";

/**
 * Facet counts, each computed with that facet's *own* selection excluded.
 *
 * This is disjunctive faceting, and it is what makes a multi-select filter
 * usable. Counting a facet under its own selection means that ticking "Polygon"
 * drops Point and Line to zero — the other values of the box you are standing in
 * disappear, so you cannot widen the choice you just made without undoing it
 * first. Everyone who does faceted search well does this: CARTO tags a widget's
 * filters with an `owner` and has the widget skip filters matching its own
 * `filterOwner`, Algolia calls it disjunctive faceting, and Elasticsearch does it
 * with `post_filter`.
 *
 * The effect: selecting "Polygon" narrows the results and every *other* facet's
 * counts, while Geometry type keeps showing what Point and Line would give if you
 * ticked them too.
 *
 * **Request shape.** Facets without a selection all share one `/aggregate` call,
 * because nothing distinguishes their filter sets. Only a facet that is actually
 * selected needs its own call. With nothing selected that is one request — the
 * same as before — and with two filters on it is three.
 */
export const useCatalogFacetBuckets = ({
  facets,
  params,
}: {
  /** Aggregation name and the parameter that narrows it (`goat:filter_param`). */
  facets: { name: string; param: string }[];
  /** The current filters, without paging or sorting. */
  params: CatalogSearchParams;
}) => {
  /**
   * Every value each facet can take, unfiltered.
   *
   * This is what keeps the sidebar still. `/aggregate` returns only the buckets
   * that exist under the current filters, so without a baseline the rows
   * *disappear* as you filter — the panel would promise a greyed-out "Raster 0"
   * and instead show nothing at all, and the list would reshuffle under the
   * cursor on every tick. Filtering the filters is the thing that makes faceted
   * search feel broken.
   *
   * One request, no filters, and it only changes when the mirror is rebuilt — so
   * it is cached for an hour like the discovery call.
   */
  const { data: baseline } = useSWR<Record<string, CatalogAggregationBucket[]>>(
    facets.length && CATALOG_API_BASE_URL
      ? ["catalog-facet-universe", facets.map((facet) => facet.name).join(",")]
      : null,
    async () => {
      const url = `${CATALOG_API_BASE_URL}/aggregate?unit=collections&aggregations=${facets
        .map((facet) => facet.name)
        .join(",")}`;
      const response = (await fetcher(url)) as CatalogAggregations;
      const buckets: Record<string, CatalogAggregationBucket[]> = {};
      for (const aggregation of response.aggregations ?? []) {
        buckets[aggregation.name] = aggregation.buckets ?? [];
      }
      return buckets;
    },
    { revalidateOnFocus: false, dedupingInterval: 60 * 60 * 1000 }
  );

  const isSelected = (param: string) => {
    const value = params[param];
    return Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null;
  };

  const shared = facets.filter((facet) => !isSelected(facet.param));
  const own = facets.filter((facet) => isSelected(facet.param));

  /**
   * One request per distinct filter set. Serialised into the SWR key so the cache
   * turns over exactly when a filter changes.
   */
  const plan = [
    ...(shared.length
      ? [{ names: shared.map((facet) => facet.name), query: buildCatalogQuery(params) }]
      : []),
    ...own.map((facet) => ({
      names: [facet.name],
      query: buildCatalogQuery({ ...params, [facet.param]: undefined }),
    })),
  ];

  const { data, isLoading, error } = useSWR<Record<string, CatalogAggregationBucket[]>>(
    plan.length && CATALOG_API_BASE_URL ? ["catalog-facets", JSON.stringify(plan)] : null,
    async () => {
      const results = await Promise.all(
        plan.map(async (step) => {
          const separator = step.query ? "&" : "?";
          const url = `${CATALOG_API_BASE_URL}/aggregate${step.query}${separator}aggregations=${step.names.join(",")}`;
          const response = (await fetcher(url)) as CatalogAggregations;
          return response.aggregations ?? [];
        })
      );
      const buckets: Record<string, CatalogAggregationBucket[]> = {};
      for (const aggregations of results) {
        for (const aggregation of aggregations) {
          buckets[aggregation.name] = aggregation.buckets ?? [];
        }
      }
      return buckets;
    },
    // Keep the previous counts on screen while the next ones load, so the sidebar
    // does not blank out on every tick.
    { keepPreviousData: true }
  );

  /**
   * The value universe, carrying current counts — zero for a value the filters
   * exclude. Order comes from the baseline (frequency descending), so rows never
   * move as counts change.
   */
  const buckets: Record<string, CatalogAggregationBucket[]> = {};
  for (const facet of facets) {
    const current = new Map(
      (data?.[facet.name] ?? []).map((bucket) => [bucket.key, bucket] as const)
    );
    const universe = baseline?.[facet.name];
    if (!universe) {
      // Until the baseline lands, show what the filtered query returned rather
      // than nothing.
      buckets[facet.name] = data?.[facet.name] ?? [];
      continue;
    }
    buckets[facet.name] = universe.map(
      (bucket) => current.get(bucket.key) ?? { ...bucket, frequency: 0 }
    );
  }

  return { buckets, isLoading, isError: error };
};
