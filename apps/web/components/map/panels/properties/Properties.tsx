import { Divider, Link, Stack, Typography } from "@mui/material";
import { formatDistance } from "date-fns";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useDateFnsLocale } from "@/i18n/utils";

import type { ProjectLayer } from "@/lib/validations/project";

import { isCatalogLayer } from "@/lib/utils/catalog-layer";
import { datasetUpdatedAt } from "@/lib/utils/datasetDates";

import DatasetSummary from "@/components/dashboard/dataset/DatasetSummary";

/** The catalog entry this layer was promoted from, if it was. */
const catalogEntryId = (layer: ProjectLayer): string | undefined => {
  const id = (layer.other_properties as { catalog_item?: { id?: string } } | undefined)
    ?.catalog_item?.id;
  return typeof id === "string" && id ? id : undefined;
};

/** One labelled row, in the same three parts as every field above it. */
const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <Stack spacing={1}>
    <Typography variant="caption">{label}</Typography>
    <Divider />
    {children}
  </Stack>
);

const PropertiesPanel = ({ activeLayer }: { activeLayer: ProjectLayer }) => {
  const { t } = useTranslation("common");
  const dateLocale = useDateFnsLocale();
  const updatedAt = datasetUpdatedAt(activeLayer);
  const entryId = catalogEntryId(activeLayer);
  return (
    <>
      <Stack spacing={4} sx={{ p: 2 }}>
        <DatasetSummary dataset={activeLayer} hideEmpty={true} hideMainSection={true} />

        {/* Where the layer came from. The tab already carries the publisher and
            the licence; what was missing is that this is someone else's
            dataset, and the way back to the entry it was taken from. */}
        {isCatalogLayer(activeLayer) && (
          <Field label={t("source")}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Icon iconName={ICON_NAME.GLOBE} style={{ fontSize: 13 }} htmlColor="inherit" />
              <Typography variant="body2">{t("catalog")}</Typography>
              {entryId && (
                <>
                  <Typography variant="body2" color="text.disabled">
                    ·
                  </Typography>
                  <Link
                    variant="body2"
                    href={`/catalog/${encodeURIComponent(entryId)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    underline="hover">
                    {t("catalog_open_entry")}
                  </Link>
                </>
              )}
            </Stack>
          </Field>
        )}

        {updatedAt && (
          <Field label={t("last_updated")}>
            <Typography variant="body2">
              {formatDistance(new Date(updatedAt), new Date(), {
                addSuffix: true,
                locale: dateLocale,
              })}
            </Typography>
          </Field>
        )}
      </Stack>
    </>
  );
};

export default PropertiesPanel;
