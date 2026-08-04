"use client";

import { Box, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import type { CatalogColumn } from "@/lib/validations/catalog";

/**
 * A dataset's columns — STAC `table:columns` — as the prototype's data
 * dictionary: monospaced names, the storage type, and what each column means.
 *
 * The description column is dropped when no column has one. The catalog
 * currently publishes names and partial types but no per-column descriptions
 * (harvester contract), and a third column of empty cells reads as missing data
 * rather than as an absent field.
 *
 * Scrolls inside itself: a 60-column dataset must not widen the page.
 */
const CatalogSchemaTable = ({ columns }: { columns: CatalogColumn[] }) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  const withDescription = columns.some((column) => !!column.description);
  // Without descriptions the two remaining columns still stay left, against a
  // filler track — a type stranded at the far edge of the card reads as a
  // different row.
  const template = withDescription
    ? "200px 110px minmax(320px, 1fr)"
    : "minmax(200px, 360px) 140px 1fr";
  const minWidth = withDescription ? 692 : undefined;

  const cell = {
    display: "grid",
    gridTemplateColumns: template,
    gap: 3.5,
    minWidth,
    px: 3.5,
  } as const;

  return (
    <Box
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 2,
        overflowX: "auto",
        overflowY: "hidden",
      }}>
      <Box
        sx={{
          ...cell,
          py: 2.5,
          backgroundColor: theme.palette.action.hover,
          borderBottom: `1px solid ${theme.palette.divider}`,
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 0.4,
          textTransform: "uppercase",
          color: theme.palette.text.secondary,
        }}>
        <Box>{t("catalog_column_name")}</Box>
        <Box>{t("catalog_column_type")}</Box>
        {withDescription && <Box>{t("catalog_column_description")}</Box>}
      </Box>
      {columns.map((column, index) => (
        <Box
          key={column.name}
          sx={{
            ...cell,
            py: 2.75,
            alignItems: "baseline",
            borderBottom:
              index < columns.length - 1 ? `1px solid ${theme.palette.divider}` : "none",
          }}>
          <Typography
            sx={{ fontSize: 13, fontWeight: 600, fontFamily: "ui-monospace, monospace" }}>
            {column.name}
          </Typography>
          <Typography
            sx={{
              fontSize: 12,
              fontFamily: "ui-monospace, monospace",
              color: theme.palette.text.secondary,
            }}>
            {column.type || "—"}
          </Typography>
          {withDescription && (
            <Typography sx={{ fontSize: 12.5, color: theme.palette.text.secondary }}>
              {column.description}
            </Typography>
          )}
        </Box>
      ))}
    </Box>
  );
};

export default CatalogSchemaTable;
