"use client";

import { Box, Button, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { catalogKindOf } from "@/lib/catalog/kind";
import type { CatalogCollection, CatalogItem } from "@/lib/validations/catalog";

import { datasetPeriod, itemPeriod } from "@/lib/catalog/period";

import { describedBy, linkHref, useCatalogLabels } from "@/hooks/catalog/useCatalogLabels";

import {
  BUNDLE_ACCENT,
  DetailHeader,
  DetailTabs,
  KeywordChips,
  LicenseBadge,
  MetaSidebar,
  SectionCard,
  type MetaField,
} from "@/components/dashboard/catalog/CatalogDetailChrome";
import CatalogFootprintMap from "@/components/dashboard/catalog/CatalogFootprintMap";
import CatalogProviderCard from "@/components/dashboard/catalog/CatalogProviderCard";
import CatalogSchemaTable from "@/components/dashboard/catalog/CatalogSchemaTable";

/**
 * One dataset, following the prototype's `LayerDetail` (`catalog.jsx`): a
 * description with its keywords and a map beneath it, the metadata as a column
 * beside them, and the columns on a second tab.
 *
 * Three points where the prototype and the live catalog differ, each resolved in
 * favour of what the data supports:
 *
 * - **The map is inline, not a tab.** The prototype only gives tabular data its
 *   own Map tab, and a footprint is context for the description rather than a
 *   destination. A dataset with no geometry (94 of the current items) simply has
 *   no map card.
 * - **Description and keywords come from the parent collection**, because that is
 *   where the harvester publishes them — see `describedBy`.
 * - **Download is not offered.** Every asset the mirror holds lives in GOAT's own
 *   storage and is stripped from responses (design S14), so a download button
 *   would have nothing to fetch. Adding the dataset to a project is the intended
 *   route to the data (promote-on-use) and is shown as the primary action,
 *   disabled until that lands; the provider's own record stays reachable through
 *   the Provider card.
 */

type TabId = "summary" | "data";

const CatalogLayerDetail = ({
  item,
  collection,
  onBack,
  backLabel,
  starred,
  onToggleStar,
}: {
  item: CatalogItem;
  /** The item's parent, which carries description, keywords and providers. */
  collection?: CatalogCollection;
  onBack: () => void;
  backLabel?: string;
  starred?: boolean;
  onToggleStar?: () => void;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const labels = useCatalogLabels();
  const [tab, setTab] = useState<TabId>("summary");

  const props = item.properties;
  const { description, keywords } = describedBy(item, collection);
  const columns = props["table:columns"] ?? [];
  const hasMap = !!item.geometry;
  const memberCount = (collection?.["goat:member_count"] as number | undefined) ?? 1;
  const inBundle = memberCount > 1;
  /**
   * Inside a bundle, the layer's own title is what distinguishes it from its
   * siblings ("… SHP EPSG:31259"). On its own, the layer *is* the dataset, so the
   * dataset's name is the right one — and it is the name the card that led here
   * showed. 60 of the catalog's representative titles carry a format suffix the
   * collection title does not.
   */
  const title = inBundle ? props.title : collection?.title || props.title;
  // `other` is STAC's "unknown", not a licence — see `licenseLabel`.
  const licenseLabel = labels.licenseLabel(props.license);

  const tabs = useMemo(() => {
    const list: { id: TabId; label: string; count?: number }[] = [
      { id: "summary", label: t("summary") },
    ];
    if (columns.length > 0) {
      list.push({ id: "data", label: t("data"), count: columns.length });
    }
    return list;
  }, [columns.length, t]);

  const fields: (MetaField | false | undefined)[] = [
    {
      icon: ICON_NAME.LAYERS,
      label: t("metadata.headings.type"),
      // Resolved with `asMember`, so a layer inside a bundle reports its own kind
      // rather than the "bundle" its collection stamped on it.
      value: labels.kindLabel(catalogKindOf(item, inBundle)),
    },
    !!props["goat:geometryType"] && {
      icon: ICON_NAME.MAP,
      label: t("metadata.headings.geometry_type"),
      value: labels.geometryLabel(props["goat:geometryType"]),
    },
    {
      icon: ICON_NAME.DATA_CATEGORY,
      label: t("metadata.headings.data_category"),
      value: labels.categoryLabel(props.themes),
    },
    {
      icon: ICON_NAME.GLOBE,
      label: t("metadata.headings.geographical_code"),
      value: labels.regionLabel(props["goat:geographical_code"]),
    },
    {
      icon: ICON_NAME.LANGUAGE,
      label: t("metadata.headings.language"),
      value: labels.languageLabel(props.language?.code),
    },
    // The one row the prototype's sidebar does not list. Row count is published
    // on nearly every item and is the number that decides whether a dataset is
    // worth opening, and the prototype shows it on its cards — which the live
    // data cannot fill, because a dataset card stands for all of its layers.
    {
      icon: ICON_NAME.TABLE,
      label: t("catalog_row_count"),
      value: labels.formatCount(props["table:row_count"]),
    },
    !!licenseLabel && {
      icon: ICON_NAME.LICENSE,
      label: t("metadata.headings.license"),
      value: <LicenseBadge license={licenseLabel} href={linkHref(item.links, "license")} />,
    },
    {
      icon: ICON_NAME.DATABASE,
      label: t("metadata.headings.lineage"),
      value: props["processing:lineage"] as string | undefined,
    },
    // The data's OWN date, where the source states one. Read as a period rather
    // than as `properties.datetime`: an item covering a range publishes
    // `start_datetime`/`end_datetime` and sets `datetime` to null, so the single
    // field is empty for exactly the datasets that have the most to say about
    // when they are from. Dropped entirely where nothing is stated (see
    // `MetaSidebar`) rather than shown empty.
    //
    // A lone layer reads its DATASET's period, for the same reason it takes the
    // dataset's title and description: the two are one thing, and the Collection
    // is where a conformant harvest states coverage. Where they disagree the
    // extent is the broader of the two by definition (it is the envelope of the
    // items), so this shows the period the data covers rather than one date
    // inside it — 8 collections in the current bucket differ that way. Inside a
    // bundle the layer's own date is the honest answer, since the dataset's is
    // already on the bundle page.
    {
      icon: ICON_NAME.CALENDAR,
      label: t("catalog_datetime"),
      value: labels.formatPeriod(
        inBundle ? itemPeriod(item) : datasetPeriod(collection, [item])
      ),
    },
    {
      icon: ICON_NAME.CLOCK,
      label: t("catalog_updated"),
      value: labels.formatDate(props.updated),
    },
  ];

  return (
    <>
      <DetailHeader
        onBack={onBack}
        backLabel={backLabel}
        title={title}
        badge={
          inBundle && collection
            ? {
                label: t("catalog_part_of_bundle", { bundle: collection.title || collection.id }),
                color: BUNDLE_ACCENT,
                plain: true,
              }
            : null
        }
        actions={
          <>
            {onToggleStar && (
              <Button
                variant="outlined"
                color={starred ? "primary" : "inherit"}
                onClick={onToggleStar}
                startIcon={
                  <Icon
                    iconName={ICON_NAME.STAR}
                    style={{ fontSize: 13 }}
                    htmlColor={starred ? theme.palette.primary.main : theme.palette.text.secondary}
                  />
                }
                sx={starred ? { backgroundColor: theme.palette.action.hover } : undefined}>
                {starred ? t("catalog_saved") : t("save")}
              </Button>
            )}
            <Tooltip title={t("catalog_tab_coming_soon")} placement="top">
              {/* A disabled button emits no pointer events, so the tooltip needs
                  a wrapper to hang off. */}
              <Box component="span" sx={{ display: "inline-flex" }}>
                <Button
                  variant="contained"
                  disabled
                  startIcon={<Icon iconName={ICON_NAME.PLUS} style={{ fontSize: 13 }} />}>
                  {t("catalog_add_to_project")}
                </Button>
              </Box>
            </Tooltip>
          </>
        }
      />

      <DetailTabs<TabId> tabs={tabs} active={tab} onChange={setTab} />

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={6}
        alignItems="flex-start"
        sx={{ mb: 10 }}>
        <Stack spacing={4} sx={{ flex: 1, minWidth: 0, alignSelf: "stretch" }}>
          {tab === "summary" && (
            <>
              <SectionCard title={t("metadata.headings.description")}>
                {description ? (
                  <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                    {description}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {t("catalog_no_description")}
                  </Typography>
                )}
                {!!keywords?.length && (
                  <Box sx={{ mt: 4.5, pt: 4, borderTop: `1px solid ${theme.palette.divider}` }}>
                    <Typography
                      sx={{
                        fontSize: 11,
                        fontWeight: 700,
                        letterSpacing: 0.5,
                        textTransform: "uppercase",
                        color: theme.palette.text.secondary,
                        mb: 2.5,
                      }}>
                      {t("catalog_keywords")}
                    </Typography>
                    <KeywordChips keywords={keywords} />
                  </Box>
                )}
              </SectionCard>

              {hasMap && (
                <Box
                  sx={{
                    position: "relative",
                    flex: { xs: "none", md: 1 },
                    minHeight: { xs: 320, md: 260 },
                    borderRadius: 2.5,
                    overflow: "hidden",
                    border: `1px solid ${theme.palette.divider}`,
                    boxShadow: theme.shadows[1],
                  }}>
                  <CatalogFootprintMap item={item} fill />
                </Box>
              )}
            </>
          )}

          {tab === "data" && (
            <SectionCard title={t("catalog_columns")} note={t("catalog_columns_note")}>
              <CatalogSchemaTable columns={columns} />
            </SectionCard>
          )}
        </Stack>

        {tab === "summary" && (
          <MetaSidebar fields={fields}>
            <CatalogProviderCard
              providers={collection?.providers}
              publisher={props["goat:publisher"]}
              sourceHref={linkHref(item.links, "via")}
            />
          </MetaSidebar>
        )}
      </Stack>
    </>
  );
};

export default CatalogLayerDetail;
