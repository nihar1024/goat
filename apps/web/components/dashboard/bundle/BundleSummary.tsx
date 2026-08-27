import { Divider, Link, Stack, Typography, styled, useTheme } from "@mui/material";
import { format } from "date-fns";
import React from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useDateFnsLocale } from "@/i18n/utils";

import type { BundleDependency, BundleRead } from "@/lib/api/bundles";

import { useGetMetadataValueTranslation } from "@/hooks/map/DatasetHooks";

import { METADATA_HEADER_ICONS } from "@/lib/constants/metadataIcons";

const ContainerWrapper = styled("div")({
  containerType: "inline-size",
  width: "100%",
});

const LayoutContainer = styled("div")({
  display: "flex",
  flexDirection: "row",
  gap: "16px",
  width: "100%",
  "@container (max-width: 600px)": {
    flexDirection: "column",
  },
});

const MetadataSection = styled("div")({
  flex: 4,
  order: 1,
  "@container (max-width: 600px)": {
    order: 2,
    flex: "1 1 100%",
  },
});

const MainContentSection = styled("div")({
  flex: 1,
  order: 2,
  "@container (max-width: 600px)": {
    order: 1,
    flex: "1 1 100%",
  },
});

/** Scalar provenance fields, as rendered on the summary. */
type MetadataField =
  | "description"
  | "geographical_code"
  | "data_reference_year"
  | "lineage"
  | "license"
  | "attribution"
  | "distributor_name"
  | "distributor_email"
  | "distribution_url";

interface BundleSummaryProps {
  bundle: BundleRead;
  dependencies?: BundleDependency[];
}

const BundleSummary: React.FC<BundleSummaryProps> = ({ bundle, dependencies }) => {
  const theme = useTheme();
  const { t, i18n } = useTranslation("common");
  const getMetadataValueTranslation = useGetMetadataValueTranslation();
  const dateLocale = useDateFnsLocale();

  // The same aggregated fields a layer summarises, minus the two that classify a
  // layer rather than a dataset (data_category, language_code). Icons, headings
  // and value translation all go through the layer helpers so the two summaries
  // cannot drift apart. `type` resolves via metadata.type.<bundle_type>.
  const aggregatedFields = ["type", "geographical_code", "distributor_name", "license"] as const;

  // Statuses arrive as the backend's lowercase enum value ("ready"). Translated
  // where a label exists, capitalised otherwise so a status added later still
  // reads as a label rather than raw data.
  const statusLabel = bundle.status
    ? i18n.exists(`common:${bundle.status}`)
      ? t(bundle.status)
      : bundle.status.charAt(0).toUpperCase() + bundle.status.slice(1)
    : undefined;

  // Bundle-specific, so they have no aggregated-field equivalent to reuse.
  const bundleAttributes: { key: string; heading: string; value?: string; icon: ICON_NAME }[] = [
    { key: "status", heading: t("status"), value: statusLabel, icon: ICON_NAME.CIRCLEINFO },
    {
      key: "created_at",
      heading: t("created_at"),
      value: bundle.created_at ? format(new Date(bundle.created_at), "P", { locale: dateLocale }) : undefined,
      icon: ICON_NAME.CALENDAR,
    },
  ];

  // Same field vocabulary as a layer's summary, restricted to what describes a
  // whole acquisition. Rendered whether set or not, so an empty licence reads as
  // "not stated" rather than being invisible.
  const metadataFields: { field: MetadataField; heading: string; type: "text" | "email" | "url" }[] = [
    { field: "description", heading: t("metadata.headings.description"), type: "text" },
    { field: "geographical_code", heading: t("metadata.headings.geographical_code"), type: "text" },
    { field: "data_reference_year", heading: t("metadata.headings.data_reference_year"), type: "text" },
    { field: "lineage", heading: t("metadata.headings.lineage"), type: "text" },
    { field: "license", heading: t("metadata.headings.license"), type: "text" },
    { field: "attribution", heading: t("metadata.headings.attribution"), type: "text" },
    { field: "distributor_name", heading: t("metadata.headings.distributor_name"), type: "text" },
    { field: "distributor_email", heading: t("metadata.headings.distributor_email"), type: "email" },
    { field: "distribution_url", heading: t("metadata.headings.distribution_url"), type: "url" },
  ];

  return (
    <ContainerWrapper>
      <LayoutContainer>
        <MetadataSection>
          <Stack spacing={4} sx={{ width: "100%" }}>
            {metadataFields.map(({ field, heading, type }) => {
              // Description is the bundle's own column; the rest live in the
              // provenance document.
              const value =
                field === "description" ? bundle.description : bundle.dataset_metadata?.[field];
              return (
                <Stack key={field} spacing={1}>
                  <Typography variant="caption">{heading}</Typography>
                  <Divider />
                  {!value && (
                    <Typography variant="body2" sx={{ fontStyle: "italic" }}>
                      {t(`metadata.no_metadata_available.${field}`)}
                    </Typography>
                  )}
                  {!!value && type === "email" && (
                    <Link href={`mailto:${value}`} target="_blank" rel="noopener noreferrer">
                      {String(value)}
                    </Link>
                  )}
                  {!!value && type === "url" && (
                    <Link href={String(value)} target="_blank" rel="noopener noreferrer">
                      {String(value)}
                    </Link>
                  )}
                  {!!value && type === "text" && <Typography variant="body2">{String(value)}</Typography>}
                </Stack>
              );
            })}

            {!!dependencies?.length && (
              <Stack spacing={1}>
                <Typography variant="caption">{t("bundle_dependencies")}</Typography>
                <Divider />
                {dependencies.map((dependency) => (
                  <Stack
                    key={`${dependency.dependency_kind}-${dependency.depends_on_bundle_id}`}
                    direction="row"
                    spacing={2}
                    alignItems="center">
                    <Icon
                      iconName={ICON_NAME.LINK}
                      style={{ fontSize: 14 }}
                      htmlColor={theme.palette.text.secondary}
                    />
                    <Link href={`/bundles/${dependency.depends_on_bundle_id}`} variant="body2">
                      {dependency.depends_on_name}
                    </Link>
                    <Typography variant="caption" color="text.secondary">
                      {i18n.exists(`common:${dependency.depends_on_type}`)
                        ? t(dependency.depends_on_type)
                        : dependency.depends_on_type}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            )}
          </Stack>
        </MetadataSection>

        <MainContentSection>
          <Stack spacing={2}>
            {aggregatedFields.map((key) => (
              <div key={key} style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <Icon
                  iconName={METADATA_HEADER_ICONS[key]}
                  style={{ fontSize: 14, flexShrink: 0 }}
                  htmlColor={theme.palette.text.secondary}
                />
                <div style={{ minWidth: 0 }}>
                  <Typography variant="caption" noWrap>
                    {i18n.exists(`common:metadata.headings.${key}`)
                      ? t(`common:metadata.headings.${key}`)
                      : key}
                  </Typography>
                  <Typography variant="body2" fontWeight="bold" noWrap>
                    {getMetadataValueTranslation(
                      key,
                      key === "type"
                        ? bundle.bundle_type
                        : (bundle.dataset_metadata?.[key] ?? "")
                    )}
                  </Typography>
                </div>
              </div>
            ))}
            {bundleAttributes.map(({ key, heading, value, icon }) => (
              <div key={key} style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <Icon
                  iconName={icon}
                  style={{ fontSize: 14, flexShrink: 0 }}
                  htmlColor={theme.palette.text.secondary}
                />
                <div style={{ minWidth: 0 }}>
                  <Typography variant="caption" noWrap>
                    {heading}
                  </Typography>
                  <Typography variant="body2" fontWeight="bold" noWrap>
                    {value ?? " — "}
                  </Typography>
                </div>
              </div>
            ))}
          </Stack>
        </MainContentSection>
      </LayoutContainer>
    </ContainerWrapper>
  );
};

export default BundleSummary;
