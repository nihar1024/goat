"use client";

import {
  Box,
  Button,
  Chip,
  Container,
  Drawer,
  Grid,
  IconButton,
  Pagination,
  Skeleton,
  Stack,
  Typography,
  debounce,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useCatalogAggregations, useCatalogDatasets } from "@/lib/api/catalog";
import { datasetCard } from "@/lib/catalog/card";
import type { CatalogCollection } from "@/lib/validations/catalog";

import { useCatalogFacetBuckets } from "@/hooks/catalog/useCatalogFacetBuckets";
import { CATALOG_PAGE_SIZE, useCatalogSearchState } from "@/hooks/catalog/useCatalogSearchState";
import { useGetMetadataValueTranslation } from "@/hooks/map/DatasetHooks";

import EmptySection from "@/components/common/EmptySection";
import CatalogCard from "@/components/dashboard/catalog/CatalogCard";
import CatalogFilterPanel from "@/components/dashboard/catalog/CatalogFilterPanel";
import CatalogSpatialSection from "@/components/dashboard/catalog/CatalogSpatialSection";
import CatalogTabs from "@/components/dashboard/catalog/CatalogTabs";
import CatalogToolbar from "@/components/dashboard/catalog/CatalogToolbar";

/**
 * The catalog: search, filter and browse the datasets served by the STAC API
 * (apps/catalog). Replaces the previous page, which read `customer.layer` rows
 * flagged `in_catalog`.
 *
 * Two properties are deliberate:
 *
 * **The URL is the only state.** Filters, search, sort, page and view all live
 * in the query string (`useCatalogSearchState`), so a pasted link reproduces a
 * view exactly. The old page kept the same state twice — in `nuqs` and in a
 * React object every toggle had to update by hand.
 *
 * **The facet list is not written down anywhere in the client.** It comes from
 * `/stac/aggregations`, which reports each facet's name *and* the parameter
 * that narrows it (`goat:filter_param`). A facet added server-side appears
 * here; one whose column the harvester dropped stops being offered. That
 * matters: the name is not the parameter — `category_count` is narrowed with
 * `?themes=`.
 */

/** Icons per facet parameter. Falls back to a neutral filter glyph. */
const FACET_ICONS: Record<string, ICON_NAME> = {
  type: ICON_NAME.LAYERS,
  geometry_type: ICON_NAME.POLYGON_FEATURE,
  themes: ICON_NAME.DATA_CATEGORY,
  publisher: ICON_NAME.ORGANIZATION,
  language: ICON_NAME.LANGUAGE,
  license: ICON_NAME.LICENSE,
};

/** Facets whose buckets are too sparse to be worth a sidebar section. */
const MIN_BUCKETS_TO_OFFER = 2;

/** Sort orders the catalog offers. `-` prefixes a descending `sortby`. */
const SORT_OPTIONS: { value: string; labelKey: string; icon: ICON_NAME }[] = [
  { value: "-updated", labelKey: "sort_last_updated", icon: ICON_NAME.REFRESH },
  { value: "title", labelKey: "sort_title_asc", icon: ICON_NAME.SORT_ALPHA_ASC },
  { value: "-title", labelKey: "sort_title_desc", icon: ICON_NAME.SORT_ALPHA_DESC },
];

/**
 * Filter parameters whose values the app already has a vocabulary for, under a
 * different name than the parameter: `?themes=` selects a data category, and
 * `?language=` a language code.
 */
const FACET_VOCABULARY: Record<string, string> = {
  themes: "data_category",
  language: "language_code",
};

/**
 * Sidebar headings that differ from the metadata field names.
 *
 * `metadata.headings.*` names *fields on a record* — "Geometry type" / "Geometrietyp"
 * is right on a detail page, and is the term the UI glossary fixes for the workflow
 * parameter. As a pair of filter categories they read badly: "Typ" next to
 * "Geometrietyp" makes a reader work out which type is which. A browse filter wants
 * the shorter noun, so the catalog labels these two "Data type" and "Geometry".
 */
const FACET_LABEL_KEYS: Record<string, string> = {
  type: "catalog_facet_type",
  geometry_type: "catalog_facet_geometry",
};

/**
 * Facets the sidebar does not offer, whatever the server reports.
 *
 * `geographical_code` is a coarse label — a country or continent code — published
 * on 71 of 3,834 datasets, and every one of them says `AT` bar a single `HU`. The
 * spatial filter above it answers the same question against real geometry (a NUTS
 * region or a drawn shape, matched on the dataset's footprint), so offering this
 * as well put two "where" controls in one sidebar, one of which covers 1.9% of
 * the catalog and would disagree with the other.
 *
 * Hidden here rather than dropped server-side: the aggregation and the
 * `?geographical_code=` filter stay part of the API, which other clients and the
 * MCP tools use, and a metadata row on a detail page still states the value where
 * a dataset publishes one. This only decides what the browse sidebar offers.
 */
const FACET_HIDDEN = new Set(["geographical_code"]);

/**
 * Sidebar order, most-asked question first.
 *
 * The server returns aggregations in mirror-column order, which put Geometry above
 * Data type and left the date range stranded near the top. Browsing a data catalog
 * asks in roughly this sequence: where is it, what is it about, what kind of thing
 * is it (and then which geometry), whose is it, may I use it, and only last — when
 * is it from, which is also the least populated field (`datetime` is null on 52%
 * of items). Anything the server adds that is not listed keeps its own position at
 * the end.
 */
const FACET_ORDER = ["themes", "type", "geometry_type", "publisher", "license", "language"];

/**
 * A dataset row. The adapter lives here rather than inline at both call sites so
 * the grid and the list cannot drift.
 */
const DatasetCard = ({
  dataset,
  view,
  compact,
  starred,
  onToggleStar,
  onOpen,
}: {
  dataset: CatalogCollection;
  view?: "list" | "grid";
  compact?: boolean;
  starred: boolean;
  onToggleStar: (id: string) => void;
  onOpen: (href: string) => void;
}) => {
  const card = datasetCard(dataset);
  return (
    <CatalogCard
      card={card}
      view={view}
      compact={compact}
      starred={starred}
      onToggleStar={() => onToggleStar(dataset.id)}
      onClick={() => onOpen(card.href)}
      onOpenMember={(memberId) => onOpen(`/catalog/${encodeURIComponent(memberId)}`)}
    />
  );
};

const CatalogPage = () => {
  const { t, i18n } = useTranslation("common");
  const router = useRouter();
  const theme = useTheme();
  /** Below `md` the sidebar becomes a drawer — see the Grid below. */
  const isCompact = useMediaQuery(theme.breakpoints.down("md"));
  /** Below `sm` the toolbar and the cards switch to their phone layouts. */
  const isPhone = useMediaQuery(theme.breakpoints.down("sm"));
  const [filtersOpen, setFiltersOpen] = useState(false);
  /**
   * Facet values are shown through the app's own vocabularies, so the sidebar
   * says "Bundle" and "Austria" where the served buckets say `bundle` and `AT` —
   * matching what the cards beside them show. Untranslated values pass through.
   */
  const translateMetadataValue = useGetMetadataValueTranslation();
  const facetOptionLabel = useCallback(
    (param: string, value: string) =>
      translateMetadataValue(FACET_VOCABULARY[param] ?? param, value),
    [translateMetadataValue]
  );

  const { aggregations: served, isLoading: discoveryLoading } = useCatalogAggregations();
  const aggregations = useMemo(
    () => served.filter((a) => !FACET_HIDDEN.has(a["goat:filter_param"] ?? "")),
    [served]
  );
  const {
    view,
    page,
    spatial,
    facetSelections,
    activeFilterCount,
    searchParams,
    facetQueryParams,
    setQ,
    setSort,
    setPage,
    setView,
    setSpatial,
    setDateRange,
    toggleFacet,
    clearAll,
    state,
  } = useCatalogSearchState({ aggregations });

  /**
   * Selected NUTS regions. Held in the URL as one comma-separated value so a
   * filtered catalog is shareable, and split here for the chips.
   */
  /**
   * Saved datasets. Local until core has somewhere to keep them: favourites are
   * user-scoped, and the design shows the control on every card, so it is wired
   * up now and persisted later rather than left out of the layout.
   */
  const [starred, setStarred] = useState<Record<string, boolean>>({});
  // Favourites live in memory until core can persist them, so filtering by
  // them is a client-side narrowing of the current page rather than a query.
  const [favouritesOnly, setFavouritesOnly] = useState(false);
  const toggleStar = useCallback(
    (id: string) => setStarred((prev) => ({ ...prev, [id]: !prev[id] })),
    []
  );

  /**
   * The facets, in the order the server offers them, each with the parameter that
   * narrows it. The parameter comes from `goat:filter_param`, never from the
   * facet's name — `category_count` is narrowed with `?themes=`.
   */
  const facetAggregations = useMemo(
    () => aggregations.filter((a) => a.name !== "total_count"),
    [aggregations]
  );
  const facetPlan = useMemo(() => {
    const plan = facetAggregations.flatMap((aggregation) => {
      const param = aggregation["goat:filter_param"];
      return param ? [{ name: aggregation.name, param }] : [];
    });
    const rank = (param: string) => {
      const index = FACET_ORDER.indexOf(param);
      return index === -1 ? FACET_ORDER.length : index;
    };
    return [...plan].sort((a, b) => rank(a.param) - rank(b.param));
  }, [facetAggregations]);

  const {
    datasets: fetchedDatasets,
    total,
    isLoading,
    isValidating,
  } = useCatalogDatasets(searchParams);

  /**
   * Favourites narrow the current page client-side, because they are held in
   * memory: the API cannot filter by them until core stores them, and sending a
   * list of ids as a query parameter would break down well before the 3,834
   * datasets a user could plausibly star.
   *
   * The consequence is honest but worth knowing: with the filter on, the result
   * count and pagination still describe the unfiltered search, so this narrows
   * *this page* rather than the catalog. That resolves itself the moment
   * favourites move server-side.
   */
  const items = useMemo(
    () =>
      favouritesOnly
        ? fetchedDatasets.filter((dataset) => starred[dataset.id])
        : fetchedDatasets,
    [fetchedDatasets, favouritesOnly, starred]
  );
  const { buckets } = useCatalogFacetBuckets({ facets: facetPlan, params: facetQueryParams });

  /** Facet sections for the sidebar. */
  /**
   * A facet's heading. Shared with the active-filter chips so a chip can say which
   * facet it came from — "Polygon" alone is clear, "Austria" next to it is not.
   */
  const facetLabel = useCallback(
    (param: string) =>
      FACET_LABEL_KEYS[param]
        ? t(FACET_LABEL_KEYS[param])
        : t(`common:metadata.headings.${param}`, param),
    [t]
  );

  const facetSections = useMemo(
    () =>
      facetPlan.flatMap(({ name, param }) => {
        const options = (buckets[name] ?? [])
          .filter((bucket) => bucket.key !== null)
          .map((bucket) => ({
            value: bucket.key as string,
            label: facetOptionLabel(param, bucket.key as string),
            count: bucket.frequency,
          }));
        if (options.length < MIN_BUCKETS_TO_OFFER) return [];
        return [
          {
            param,
            label: facetLabel(param),
            icon: FACET_ICONS[param] ?? ICON_NAME.FILTER,
            options,
          },
        ];
      }),
    [facetPlan, buckets, facetOptionLabel, facetLabel]
  );

  const debouncedSetQ = useMemo(() => debounce((value: string) => setQ(value), 500), [setQ]);

  const pageCount = total ? Math.ceil(total / CATALOG_PAGE_SIZE) : 0;
  const showSkeletons = isLoading && !items.length;
  const totalActiveFilters = activeFilterCount + (favouritesOnly ? 1 : 0);

  const filterPanel = discoveryLoading ? (
    <Skeleton variant="rectangular" height={420} />
  ) : (
    <CatalogFilterPanel
      facets={facetSections}
      selected={facetSelections}
      onToggleFacet={toggleFacet}
      activeFilterCount={totalActiveFilters}
      onClearAll={() => {
        setFavouritesOnly(false);
        clearAll();
      }}
      favouritesOnly={favouritesOnly}
      onToggleFavourites={() => setFavouritesOnly((on) => !on)}
      dateFrom={state.from}
      dateTo={state.to}
      onChangeDates={({ from, to }) => setDateRange(from ?? null, to ?? null)}
      spatialFilter={<CatalogSpatialSection filter={spatial} onChange={setSpatial} />}
      flush={isCompact}
      headerAction={
        isCompact ? (
          <IconButton size="small" aria-label={t("close")} onClick={() => setFiltersOpen(false)}>
            <Icon iconName={ICON_NAME.XCLOSE} style={{ fontSize: 13 }} />
          </IconButton>
        ) : undefined
      }
    />
  );

  return (
    <Container sx={{ py: 10, px: { xs: 4, sm: 10 } }} maxWidth="xl">
      <Stack sx={{ mb: 8 }} spacing={1}>
        <Typography variant="h6">{t("catalog")}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 640 }}>
          {t("catalog_subtitle")}
        </Typography>
      </Stack>

      <CatalogTabs active="datasets" onChange={() => undefined} datasetCount={total} />

      <Grid container justifyContent="space-between" spacing={4}>
        {/* On a phone the sidebar moves into a drawer. Stacked above the results
            it would push every dataset below the fold behind eight collapsed
            filter sections — the results are what the page is for. */}
        {!isCompact && (
          <Grid item xs={12} md={3}>
            {filterPanel}
          </Grid>
        )}

        <Grid item xs={12} md={9}>
          <Stack spacing={2}>
            <CatalogToolbar
              q={state.q ?? ""}
              onChangeQ={debouncedSetQ}
              view={view}
              onChangeView={setView}
              sort={state.sortby}
              sortOptions={SORT_OPTIONS.map((option) => ({ ...option, label: t(option.labelKey) }))}
              onChangeSort={setSort}
              onOpenFilters={isCompact ? () => setFiltersOpen(true) : undefined}
              activeFilterCount={totalActiveFilters}
              compact={isPhone}
            />

            {/* Count and active filters share ONE row. As its own row above the
                count, the chip strip appeared the moment a first filter was
                selected and pushed everything below it down 32px — a measurable
                jump on every tick. The row exists either way now. */}
            <Stack
              direction="row"
              alignItems="center"
              useFlexGap
              flexWrap="wrap"
              gap={2}
              sx={{ minHeight: 32 }}>
              <Typography variant="body2" fontWeight="bold">
                {favouritesOnly
                  ? t("catalog_n_favourites", { count: items.length })
                  : total === undefined
                    ? " "
                    : total === 0
                      ? t("n_datasets", { count: 0 })
                      : t("catalog_result_range", {
                          from: ((page - 1) * CATALOG_PAGE_SIZE + 1).toLocaleString(
                            i18n.language
                          ),
                          to: Math.min(page * CATALOG_PAGE_SIZE, total).toLocaleString(
                            i18n.language
                          ),
                          total: total.toLocaleString(i18n.language),
                        })}
              </Typography>
              {isValidating && !showSkeletons && (
                <Typography variant="caption" color="text.secondary">
                  {t("loading")}
                </Typography>
              )}
              {Object.entries(facetSelections).flatMap(([param, values]) =>
                values.map((value) => (
                  <Chip
                    key={`${param}-${value}`}
                    size="small"
                    label={`${facetLabel(param)}: ${facetOptionLabel(param, value)}`}
                    onDelete={() => toggleFacet(param, value)}
                  />
                ))
              )}
            </Stack>

            {showSkeletons && (
              <Stack spacing={4}>
                {Array.from({ length: CATALOG_PAGE_SIZE }).map((_, index) => (
                  <Skeleton key={index} variant="rectangular" height={120} />
                ))}
              </Stack>
            )}

            {/* Favourites filter in memory, so "nothing starred" is a different
                emptiness from "nothing matched" — and without its own branch the
                page rendered BLANK: `total` was still 3,834 while `items` was
                empty, so neither the results nor the empty state drew. */}
            {!showSkeletons && favouritesOnly && items.length === 0 && (
              <Stack sx={{ mt: 10 }} alignItems="center" spacing={4}>
                <EmptySection label={t("catalog_no_favourites")} icon={ICON_NAME.STAR} />
                <Typography variant="body1">{t("catalog_no_favourites_hint")}</Typography>
              </Stack>
            )}

            {!showSkeletons && !favouritesOnly && total === 0 && (
              <Stack sx={{ mt: 10 }} alignItems="center" spacing={4}>
                <EmptySection label={t("no_catalog_dataset_found")} icon={ICON_NAME.DATABASE} />
                <Typography variant="body1">{t("try_different_filters")}</Typography>
              </Stack>
            )}

            {!showSkeletons && items.length > 0 && (
              <>
                {view === "grid" ? (
                  <Box
                    sx={{
                      display: "grid",
                      gridTemplateColumns: {
                        xs: "1fr",
                        sm: "repeat(2, minmax(0, 1fr))",
                        lg: "repeat(3, minmax(0, 1fr))",
                      },
                      gap: 4,
                    }}>
                    {items.map((dataset) => (
                      <DatasetCard
                        key={dataset.id}
                        dataset={dataset}
                        view="grid"
                        compact={isPhone}
                        starred={!!starred[dataset.id]}
                        onToggleStar={toggleStar}
                        onOpen={router.push}
                      />
                    ))}
                  </Box>
                ) : (
                  <Stack spacing={4}>
                    {items.map((dataset) => (
                      <DatasetCard
                        key={dataset.id}
                        dataset={dataset}
                        compact={isPhone}
                        starred={!!starred[dataset.id]}
                        onToggleStar={toggleStar}
                        onOpen={router.push}
                      />
                    ))}
                  </Stack>
                )}

                {pageCount > 1 && (
                  <Stack direction="row" justifyContent="center" sx={{ p: 4 }}>
                    <Pagination
                      count={pageCount}
                      page={page}
                      size="large"
                      onChange={(_event, next) => setPage(next)}
                    />
                  </Stack>
                )}
              </>
            )}
          </Stack>
        </Grid>
      </Grid>

      <Drawer
        anchor="bottom"
        open={isCompact && filtersOpen}
        onClose={() => setFiltersOpen(false)}
        // Not full height: leaving the results visible behind the sheet keeps the
        // effect of each tick in view, which is the point of filtering.
        PaperProps={{ sx: { maxHeight: "85vh", borderRadius: "16px 16px 0 0" } }}>
        <Box sx={{ pt: 2, pb: 2, overflowY: "auto" }}>{filterPanel}</Box>
        <Box
          sx={{
            position: "sticky",
            bottom: 0,
            p: 3,
            borderTop: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper,
          }}>
          <Button fullWidth variant="contained" onClick={() => setFiltersOpen(false)}>
            {t("catalog_show_n_results", { count: total ?? 0 })}
          </Button>
        </Box>
      </Drawer>
    </Container>
  );
};

export default CatalogPage;
