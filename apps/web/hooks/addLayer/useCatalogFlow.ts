import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useCatalogAggregations, useCatalogDatasetPages } from "@/lib/api/catalog";
import {
  CATALOG_PAGE_SIZE,
  buildFacetParams,
  buildSearchParams,
  countActiveFilters,
} from "@/lib/catalog/searchQuery";
import type { CatalogSpatialFilter } from "@/lib/catalog/spatial";
import type { CatalogAggregation, CatalogCollection } from "@/lib/validations/catalog";

import type { FlowController } from "@/hooks/addLayer/flow";
import { FACET_HIDDEN } from "@/hooks/catalog/useCatalogFacetSections";

/**
 * Picking datasets from the catalog to add as layers.
 *
 * Filters are held in memory rather than in the URL: this runs inside a modal over
 * a project map, and a picker has no business rewriting that page's address. The
 * query itself comes from `lib/catalog/searchQuery`, the same builder the catalog
 * page uses, so both ask the API the same way.
 */

/**
 * What is selected, always as **layer** ids.
 *
 * A plain dataset contributes its own item; an open bundle contributes its members
 * individually, which is what makes "Add 3 layers" count layers rather than cards —
 * and matches promotion, where members promote one by one into a shared bundle
 * group. A locked bundle would contribute a single id, but nothing publishes one
 * yet (catalog design S11), so that branch has no data to exercise it.
 */
export type CatalogSelection = {
  ids: string[];
  toggle: (id: string) => void;
  /** Replaces the selection for a whole group — the bundle card's own checkbox. */
  setMany: (ids: string[], selected: boolean) => void;
  clear: () => void;
};

export type CatalogFlowState = {
  /**
   * Narrow to saved datasets. A filter, not a mode: it sits with the others in the
   * panel, as it does on the catalog page, and counts towards "Clear (n)".
   */
  favouritesOnly: boolean;
  toggleFavourites: () => void;
  q: string;
  setQ: (value: string) => void;
  spatial: CatalogSpatialFilter | null;
  setSpatial: (filter: CatalogSpatialFilter | null) => void;
  /** Publication period, as the panel's two date inputs hold it: `YYYY-MM-DD`. */
  dateFrom: string | null;
  dateTo: string | null;
  setDates: (range: { from: string | null; to: string | null }) => void;
  aggregations: CatalogAggregation[];
  facetSelections: Record<string, string[]>;
  toggleFacet: (param: string, value: string) => void;
  clearFilters: () => void;
  activeFilterCount: number;
  facetQueryParams: ReturnType<typeof buildFacetParams>;
  datasets: CatalogCollection[];
  total: number;
  isLoading: boolean;
  /** More results exist beyond the ones loaded. */
  hasMore: boolean;
  /** A further page is on its way, under what is already on screen. */
  isLoadingMore: boolean;
  loadMore: () => void;
  /**
   * Changes whenever the query does. The body watches it to send the list back to
   * the top — landing halfway down a freshly filtered list reads as a bug.
   */
  queryKey: string;
  selection: CatalogSelection;
  /** Saved datasets, in memory until core keeps them — as on the catalog page. */
  starred: Record<string, boolean>;
  toggleStar: (id: string) => void;
};

export type CatalogFlow = FlowController & { catalog: CatalogFlowState };

export const useCatalogFlow = ({
  onDone,
}: {
  projectId?: string;
  onDone?: () => void;
}): CatalogFlow => {
  const { t } = useTranslation("common");

  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const [q, setQValue] = useState("");

  const [spatial, setSpatialValue] = useState<CatalogSpatialFilter | null>(null);
  const [dates, setDatesValue] = useState<{ from: string | null; to: string | null }>({
    from: null,
    to: null,
  });
  const [facetSelections, setFacetSelections] = useState<Record<string, string[]>>({});
  const [ids, setIds] = useState<string[]>([]);
  const [starred, setStarred] = useState<Record<string, boolean>>({});

  const { aggregations: served } = useCatalogAggregations();
  const aggregations = useMemo(
    () => served.filter((a) => !FACET_HIDDEN.has(a["goat:filter_param"] ?? "")),
    [served]
  );

  const queryState = useMemo(
    () => ({
      q,
      sortby: "-updated",
      // The accumulating fetch owns paging; this state only describes the query.
      page: 1,
      spatial,
      from: dates.from,
      to: dates.to,
      facetSelections,
    }),
    [q, spatial, dates, facetSelections]
  );
  const searchParams = useMemo(() => buildSearchParams(queryState), [queryState]);
  const facetQueryParams = useMemo(() => buildFacetParams(searchParams), [searchParams]);
  const { datasets, total, isLoading, isLoadingMore, hasMore, loadMore, resetPages } =
    useCatalogDatasetPages(searchParams, { pageSize: CATALOG_PAGE_SIZE });

  // Narrowing a filter drops back to the first page: results already accumulated
  // belong to the old query.
  const setQ = useCallback(
    (value: string) => {
      setQValue(value);
      resetPages();
    },
    [resetPages]
  );
  const setSpatial = useCallback(
    (filter: CatalogSpatialFilter | null) => {
      setSpatialValue(filter);
      resetPages();
    },
    [resetPages]
  );
  const setDates = useCallback(
    (range: { from: string | null; to: string | null }) => {
      setDatesValue(range);
      resetPages();
    },
    [resetPages]
  );
  const toggleFavourites = useCallback(() => {
    setFavouritesOnly((on) => !on);
  }, []);
  const toggleFacet = useCallback((param: string, value: string) => {
    setFacetSelections((current) => {
      const values = current[param] ?? [];
      const next = values.includes(value)
        ? values.filter((v) => v !== value)
        : [...values, value];
      const { [param]: _dropped, ...rest } = current;
      return next.length ? { ...rest, [param]: next } : rest;
    });
    resetPages();
  }, [resetPages]);
  const clearFilters = useCallback(() => {
    setFavouritesOnly(false);
    setFacetSelections({});
    setSpatialValue(null);
    setDatesValue({ from: null, to: null });
    resetPages();
  }, [resetPages]);

  const selection = useMemo<CatalogSelection>(
    () => ({
      ids,
      toggle: (id) =>
        setIds((current) =>
          current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
        ),
      setMany: (many, selected) =>
        setIds((current) =>
          selected
            ? Array.from(new Set([...current, ...many]))
            : current.filter((value) => !many.includes(value))
        ),
      clear: () => setIds([]),
    }),
    [ids]
  );

  const toggleStar = useCallback(
    (id: string) => setStarred((current) => ({ ...current, [id]: !current[id] })),
    []
  );

  const reset = useCallback(() => {
    setFavouritesOnly(false);
    setQValue("");
    resetPages();
    setSpatialValue(null);
    setDatesValue({ from: null, to: null });
    setFacetSelections({});
    setIds([]);
  }, [resetPages]);

  /**
   * Adding is not possible yet: a catalog dataset has no layer until promote-on-use
   * materializes one, and that is backend work still to come. The action states the
   * count it *would* add, and says why it cannot — better than a tab that hides the
   * button and leaves the reader guessing.
   */
  const action = useMemo(
    () => ({
      label:
        ids.length > 1 ? t("catalog_add_n_layers", { count: ids.length }) : t("add_layer"),
      disabled: true,
      reason: t("catalog_tab_coming_soon"),
      run: () => onDone?.(),
    }),
    [ids.length, t, onDone]
  );

  return {
    steps: [],
    step: 0,
    goTo: () => undefined,
    action,
    isBusy: false,
    reset,
    catalog: {
      favouritesOnly,
      toggleFavourites,
      q,
      setQ,
      spatial,
      setSpatial,
      dateFrom: dates.from,
      dateTo: dates.to,
      setDates,
      aggregations,
      facetSelections,
      toggleFacet,
      clearFilters,
      activeFilterCount: countActiveFilters(queryState) + (favouritesOnly ? 1 : 0),
      facetQueryParams,
      datasets,
      total: total ?? 0,
      isLoading,
      // Favourites are a slice of what is loaded, so loading more of the *server's*
      // results while that filter is on would fetch pages nobody is looking at.
      hasMore: hasMore && !favouritesOnly,
      isLoadingMore,
      loadMore,
      queryKey: JSON.stringify(searchParams),
      selection,
      starred,
      toggleStar,
    },
  };
};
