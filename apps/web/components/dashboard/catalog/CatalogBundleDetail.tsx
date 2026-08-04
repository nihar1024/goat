"use client";

import { Box, Button, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { CatalogCollection, CatalogItem } from "@/lib/validations/catalog";

import { layerCard } from "@/lib/catalog/card";

import { datasetPeriod } from "@/lib/catalog/period";

import { linkHref, useCatalogLabels } from "@/hooks/catalog/useCatalogLabels";

import CatalogCard from "@/components/dashboard/catalog/CatalogCard";
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
import CatalogProviderCard from "@/components/dashboard/catalog/CatalogProviderCard";

/**
 * A bundle, following the prototype's `GroupDetail` (`catalog.jsx`): the source
 * dataset's description, then its layers as the same cards the result list uses,
 * with the shared metadata in a column beside them.
 *
 * Members are rendered as `CatalogCard`s deliberately — the prototype reuses its
 * `ListCard` here too. A member row that looked different from the same dataset
 * in search results would suggest it is a different kind of thing, when a bundle
 * is only a grouping of layers that were harvested together.
 *
 * "Save all" toggles every member at once, which is what the prototype offers:
 * nobody stars 74 layers one at a time.
 */
const CatalogBundleDetail = ({
  collection,
  members,
  onBack,
  onOpenMember,
  starred = {},
  onToggleStar,
  onToggleAll,
}: {
  collection: CatalogCollection;
  members: CatalogItem[];
  onBack: () => void;
  onOpenMember: (member: CatalogItem) => void;
  starred?: Record<string, boolean>;
  onToggleStar?: (member: CatalogItem) => void;
  onToggleAll?: (members: CatalogItem[], save: boolean) => void;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const labels = useCatalogLabels();

  const memberCount = (collection["goat:member_count"] as number | undefined) ?? members.length;

  /**
   * When the dataset's data is from: its own `extent.temporal` where it states
   * one, otherwise the span of its layers' dates.
   */
  const dataDate = labels.formatPeriod(datasetPeriod(collection, members));
  // `other` is STAC's "unknown", not a licence — see `licenseLabel`.
  const licenseLabel = labels.licenseLabel(collection.license);
  const allSaved = members.length > 0 && members.every((member) => starred[member.id]);

  const fields: (MetaField | false | undefined)[] = [
    {
      icon: ICON_NAME.LAYERS,
      label: t("metadata.headings.type"),
      value: `${t("catalog_bundle")} · ${labels.formatCount(memberCount)}`,
    },
    {
      icon: ICON_NAME.DATA_CATEGORY,
      label: t("metadata.headings.data_category"),
      value: labels.categoryLabel(collection.themes),
    },
    {
      icon: ICON_NAME.GLOBE,
      label: t("metadata.headings.geographical_code"),
      value: labels.regionLabel(collection["goat:geographical_code"]),
    },
    !!licenseLabel && {
      icon: ICON_NAME.LICENSE,
      label: t("metadata.headings.license"),
      value: (
        <LicenseBadge license={licenseLabel} href={linkHref(collection.links, "license")} />
      ),
    },
    // A Collection states its time as `extent.temporal`, and since 2026-08-04 it
    // does so on every row — so the extent wins here and the fallback to the
    // layers' own dates covers only a Collection that states nothing. Either way
    // a period renders as a period rather than as whichever endpoint came first.
    {
      icon: ICON_NAME.CALENDAR,
      label: t("catalog_datetime"),
      value: dataDate,
    },
    {
      icon: ICON_NAME.CLOCK,
      label: t("catalog_updated"),
      value: labels.formatDate(collection.updated as string | undefined),
    },
  ];

  return (
    <>
      <DetailHeader
        onBack={onBack}
        title={collection.title || collection.id}
        badge={{ label: t("catalog_bundle"), color: BUNDLE_ACCENT }}
        actions={
          <>
            {onToggleAll && members.length > 0 && (
              <Button
                variant="outlined"
                color={allSaved ? "primary" : "inherit"}
                onClick={() => onToggleAll(members, !allSaved)}
                startIcon={
                  <Icon
                    iconName={ICON_NAME.STAR}
                    style={{ fontSize: 13 }}
                    htmlColor={
                      allSaved ? theme.palette.primary.main : theme.palette.text.secondary
                    }
                  />
                }
                sx={allSaved ? { backgroundColor: theme.palette.action.hover } : undefined}>
                {allSaved ? t("catalog_all_saved") : t("catalog_save_all")}
              </Button>
            )}
            <Tooltip title={t("catalog_tab_coming_soon")} placement="top">
              <Box component="span" sx={{ display: "inline-flex" }}>
                <Button
                  variant="contained"
                  disabled
                  startIcon={<Icon iconName={ICON_NAME.PLUS} style={{ fontSize: 13 }} />}>
                  {t("catalog_add_all_to_project")}
                </Button>
              </Box>
            </Tooltip>
          </>
        }
      />

      <DetailTabs tabs={[{ id: "summary", label: t("summary") }]} active="summary" onChange={() => undefined} />

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={6}
        alignItems="flex-start"
        sx={{ mb: 10 }}>
        <Stack spacing={4} sx={{ flex: 1, minWidth: 0 }}>
          <SectionCard title={t("metadata.headings.description")}>
            {collection.description ? (
              <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                {collection.description}
              </Typography>
            ) : (
              <Typography variant="body2" color="text.secondary">
                {t("catalog_no_description")}
              </Typography>
            )}
            {!!collection.keywords?.length && (
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
                <KeywordChips keywords={collection.keywords} />
              </Box>
            )}
          </SectionCard>

          <SectionCard
            title={t("catalog_layers_in_bundle")}
            note={t("catalog_member_count", { count: memberCount })}>
            <Stack spacing={3.5}>
              {members.map((member) => (
                <CatalogCard
                  key={member.id}
                  card={layerCard(member)}
                  onClick={() => onOpenMember(member)}
                  starred={!!starred[member.id]}
                  onToggleStar={onToggleStar ? () => onToggleStar(member) : undefined}
                />
              ))}
              {members.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  {t("catalog_bundle_members_unavailable")}
                </Typography>
              )}
            </Stack>
          </SectionCard>
        </Stack>

        <MetaSidebar fields={fields}>
          <CatalogProviderCard
            providers={collection.providers}
            publisher={collection["goat:publisher"] as string | undefined}
            sourceHref={linkHref(collection.links, "via")}
          />
        </MetaSidebar>
      </Stack>
    </>
  );
};

export default CatalogBundleDetail;
