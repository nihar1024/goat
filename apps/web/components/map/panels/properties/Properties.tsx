import { Divider, Stack, Typography } from "@mui/material";
import { formatDistance } from "date-fns";
import { useTranslation } from "react-i18next";

import { useDateFnsLocale } from "@/i18n/utils";

import type { ProjectLayer } from "@/lib/validations/project";

import { datasetUpdatedAt } from "@/lib/utils/datasetDates";

import DatasetSummary from "@/components/dashboard/dataset/DatasetSummary";

const PropertiesPanel = ({ activeLayer }: { activeLayer: ProjectLayer }) => {
  const { t } = useTranslation("common");
  const dateLocale = useDateFnsLocale();
  const updatedAt = datasetUpdatedAt(activeLayer);
  return (
    <>
      <Stack spacing={4} sx={{ p: 2 }}>
        <DatasetSummary dataset={activeLayer} hideEmpty={true} hideMainSection={true} />
        {updatedAt && (
          /* Same three parts as every field above it — caption heading, rule,
             body2 value — so the panel reads as one list rather than as a
             metadata block with a differently styled footer. */
          <Stack spacing={1}>
            <Typography variant="caption">{t("last_updated")}</Typography>
            <Divider />
            <Typography variant="body2">
              {formatDistance(new Date(updatedAt), new Date(), {
                addSuffix: true,
                locale: dateLocale,
              })}
            </Typography>
          </Stack>
        )}
      </Stack>
    </>
  );
};

export default PropertiesPanel;
