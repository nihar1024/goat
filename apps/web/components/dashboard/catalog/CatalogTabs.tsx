"use client";

import { Box, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

/** The catalog's top-level tabs: label, count pill, 3px underline on the active one. */

export type CatalogTabId = "datasets" | "workflows" | "projects";

const CatalogTabs = ({
  active,
  onChange,
  datasetCount,
}: {
  active: CatalogTabId;
  onChange: (tab: CatalogTabId) => void;
  datasetCount?: number;
}) => {
  const { t, i18n } = useTranslation("common");
  const theme = useTheme();

  const tabs: { id: CatalogTabId; label: string; count?: string; enabled: boolean }[] = [
    {
      id: "datasets",
      label: t("catalog_tab_datasets"),
      count:
        typeof datasetCount === "number" ? datasetCount.toLocaleString(i18n.language) : undefined,
      enabled: true,
    },
    { id: "workflows", label: t("catalog_tab_workflows"), enabled: false },
    { id: "projects", label: t("catalog_tab_projects"), enabled: false },
  ];

  return (
    <Stack
      direction="row"
      sx={{
        borderBottom: `1px solid ${theme.palette.divider}`,
        mb: 6,
        gap: 1,
        // Three tabs do not fit a phone; scroll the rail rather than clipping the
        // last one or wrapping it onto its own line.
        overflowX: "auto",
        scrollbarWidth: "none",
        "&::-webkit-scrollbar": { display: "none" },
      }}>
      {tabs.map((tab) => {
        const selected = tab.id === active && tab.enabled;
        const button = (
          <Box
            component="button"
            type="button"
            key={tab.id}
            disabled={!tab.enabled}
            onClick={() => tab.enabled && onChange(tab.id)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 2.5,
              px: 1,
              py: 3,
              mr: 6,
              mb: "-1px",
              background: "transparent",
              border: "none",
              font: "inherit",
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: "-0.1px",
              cursor: tab.enabled ? "pointer" : "not-allowed",
              color: selected
                ? theme.palette.primary.main
                : tab.enabled
                  ? theme.palette.text.primary
                  : theme.palette.text.disabled,
              borderBottom: `3px solid ${selected ? theme.palette.primary.main : "transparent"}`,
            }}>
            {tab.label}
            {tab.count !== undefined && (
              <Typography
                component="span"
                sx={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 0.2,
                  px: 2,
                  py: 0.25,
                  borderRadius: "999px",
                  backgroundColor: selected
                    ? theme.palette.action.selected
                    : theme.palette.action.hover,
                  color: selected ? theme.palette.primary.main : theme.palette.text.secondary,
                }}>
                {tab.count}
              </Typography>
            )}
          </Box>
        );

        return tab.enabled ? (
          button
        ) : (
          <Tooltip key={tab.id} title={t("catalog_tab_coming_soon")} placement="top">
            {/* A disabled button emits no pointer events, so the tooltip needs a wrapper to hang off. */}
            <Box component="span" sx={{ display: "inline-flex" }}>
              {button}
            </Box>
          </Tooltip>
        );
      })}
    </Stack>
  );
};

export default CatalogTabs;
