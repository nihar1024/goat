"use client";

import { parseAsArrayOf, parseAsInteger, parseAsString, useQueryStates } from "nuqs";
import { useCallback, useMemo } from "react";

import type { CatalogSearchParams } from "@/lib/api/catalog";
import {
  type CatalogSpatialFilter,
  decodeSpatial,
  encodeSpatial,
  spatialGeometry,
} from "@/lib/catalog/spatial";
import type { CatalogAggregation } from "@/lib/validations/catalog";

/** URL-owned state of the catalog page, and the API query derived from it. */

/** Page size. */
export const CATALOG_PAGE_SIZE = 12;

export type CatalogView = "list" | "grid";

/** Non-facet URL parameters. */
const baseParsers = {
  q: parseAsString,
  sortby: parseAsString.withDefault("-updated"),
  /** A NUTS region id — filtered server-side by that region's geometry. */
  nuts: parseAsString,
  /** `lng,lat,km`: a buffered point. See `lib/catalog/spatial`. */
  pt: parseAsString,
  /** `lng lat;lng lat;…`: a drawn area. */
  poly: parseAsString,
  from: parseAsString,
  to: parseAsString,
  page: parseAsInteger.withDefault(1),
  view: parseAsString.withDefault("list"),
};

/** `2020-01-01` + `2024-12-31` -> `2020-01-01T00:00:00Z/2024-12-31T23:59:59Z`. */
const toDatetimeInterval = (from?: string | null, to?: string | null): string | undefined => {
  if (!from && !to) return undefined;
  const start = from ? `${from}T00:00:00Z` : "..";
  const end = to ? `${to}T23:59:59Z` : "..";
  return `${start}/${end}`;
};

export type UseCatalogSearchStateOptions = {
  /** Discovery result; supplies the facet parameter names. */
  aggregations: CatalogAggregation[];
};

export const useCatalogSearchState = ({ aggregations }: UseCatalogSearchStateOptions) => {
  /**
   * Every facet's parameter, in the order the server offers them. `total_count`
   * is not a facet and carries no parameter.
   */
  const facetParams = useMemo(
    () =>
      aggregations
        .map((a) => a["goat:filter_param"])
        .filter((param): param is string => Boolean(param)),
    [aggregations]
  );

  const parsers = useMemo(
    () => ({
      ...baseParsers,
      ...Object.fromEntries(facetParams.map((param) => [param, parseAsArrayOf(parseAsString)])),
    }),
    [facetParams]
  );

  const [state, setState] = useQueryStates(parsers);

  /** Selected values per facet parameter, for rendering checked state. */
  const facetSelections = useMemo(() => {
    const selections: Record<string, string[]> = {};
    for (const param of facetParams) {
      const value = state[param];
      if (Array.isArray(value) && value.length) selections[param] = value as string[];
    }
    return selections;
  }, [facetParams, state]);

  /** The one spatial filter in force, whichever shape it takes. */
  const spatial = useMemo(
    () => decodeSpatial({ nuts: state.nuts, pt: state.pt, poly: state.poly }),
    [state.nuts, state.pt, state.poly]
  );

  const activeFilterCount = useMemo(
    () =>
      Object.values(facetSelections).reduce((n, values) => n + values.length, 0) +
      // Every spatial shape counts as one filter, not one per parameter.
      (spatial ? 1 : 0) +
      (state.from || state.to ? 1 : 0),
    [facetSelections, spatial, state.from, state.to]
  );

  /** Toggling a value always returns to page 1: page 7 of a new result set is meaningless. */
  const toggleFacet = useCallback(
    (param: string, value: string) => {
      const current = (state[param] as string[] | null) ?? [];
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      setState({ [param]: next.length ? next : null, page: 1 });
    },
    [state, setState]
  );

  const setQ = useCallback(
    (value: string) => setState({ q: value || null, page: 1 }),
    [setState]
  );
  const setSort = useCallback((value: string) => setState({ sortby: value, page: 1 }), [setState]);
  const setPage = useCallback((page: number) => setState({ page }), [setState]);
  const setView = useCallback((view: CatalogView) => setState({ view }), [setState]);
  const setDateRange = useCallback(
    (from: string | null, to: string | null) => setState({ from, to, page: 1 }),
    [setState]
  );
  /**
   * Replace the spatial filter. The shapes are mutually exclusive — one place at
   * a time — so this always writes all three parameters and `null` clears.
   */
  const setSpatial = useCallback(
    (filter: CatalogSpatialFilter | null) =>
      setState({ ...encodeSpatial(filter), page: 1 }),
    [setState]
  );

  const clearAll = useCallback(() => {
    setState({
      ...Object.fromEntries(facetParams.map((param) => [param, null])),
      ...encodeSpatial(null),
      from: null,
      to: null,
      page: 1,
    });
  }, [facetParams, setState]);

  /** The request, for Collection Search — one row per dataset. */
  const searchParams = useMemo<CatalogSearchParams>(() => {
    // A drawn or buffered shape travels as `intersects`; a region as its id, so
    // the boundary geometry never crosses the wire.
    const geometry = spatialGeometry(spatial);
    const params: CatalogSearchParams = {
      limit: CATALOG_PAGE_SIZE,
      offset: (state.page - 1) * CATALOG_PAGE_SIZE,
      sortby: state.sortby,
      q: state.q ?? undefined,
      nuts: spatial?.kind === "region" ? spatial.nutsIds : undefined,
      intersects: geometry ? JSON.stringify(geometry) : undefined,
      datetime: toDatetimeInterval(state.from, state.to),
      ...facetSelections,
    };
    return params;
  }, [state.page, state.sortby, state.q, spatial, state.from, state.to, facetSelections]);

  /**
   * The same predicates without paging or sorting — what facet counts are
   * computed under, so a bucket count matches what selecting it would return.
   */
  const facetQueryParams = useMemo<CatalogSearchParams>(() => {
    const { limit: _limit, offset: _offset, sortby: _sortby, ...rest } = searchParams;
    // Counts have to be in the same unit as the results, or the sidebar describes a different set of things than the page: counting layers under a dataset list reported 8,166 bundles where selecting that bucket returned 1,207.
    return { ...rest, unit: "collections" };
  }, [searchParams]);

  return {
    state,
    view: (state.view === "grid" ? "grid" : "list") as CatalogView,
    page: state.page,
    /** The spatial filter in force, decoded from the URL. */
    spatial,
    facetParams,
    facetSelections,
    activeFilterCount,
    searchParams,
    facetQueryParams,
    setQ,
    setSort,
    setPage,
    setView,
    setDateRange,
    setSpatial,
    toggleFacet,
    clearAll,
  };
};
