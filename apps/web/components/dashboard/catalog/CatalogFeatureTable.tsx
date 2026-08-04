"use client";

import { Box, Typography, useTheme } from "@mui/material";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { CatalogColumn } from "@/lib/validations/catalog";

import {
  type LayerField,
  formatFeatureProperties,
} from "@/components/map/popover/formatFeatureProperties";

/**
 * The dataset's actual rows — the preview sample, one line per feature.
 *
 * The Data tab used to show only the column dictionary, which answers "what
 * fields exist" but not the question people open a dataset to ask: what does a
 * record look like. The preview already carries up to 100 features with their
 * attributes, so the rows cost nothing beyond rendering them.
 *
 * Two things it borrows rather than reinvents:
 *
 * - **Column order and labels come from `table:columns`**, so the table matches
 *   the dictionary below it and stays stable across features that happen to omit
 *   a key. Anything a feature carries that the schema does not is appended, since
 *   a value nobody declared is still a value.
 * - **Values are formatted by the app's own field formatter** — the one the map
 *   popup uses — so a number, an area or a date reads here exactly as it does
 *   everywhere else in GOAT.
 *
 * Scrolls in both directions inside its own frame: 60 columns must not widen the
 * page, and 100 rows must not push the dictionary off the screen.
 */

/**
 * Columns that are the feature's shape rather than its attributes. The preview
 * strips them from `properties` — the same set `catalog.services.preview` calls
 * non-property columns — so a table listing them would show a dash per row and
 * read as missing data.
 */
const STRUCTURAL = new Set(["geometry", "geom", "bbox"]);

/** Tall enough to read a dozen records in, short enough to leave the dictionary
 * below it reachable. */
const MAX_HEIGHT = 420;

const CatalogFeatureTable = ({
  features,
  columns,
}: {
  features: GeoJSON.Feature[];
  columns: CatalogColumn[];
}) => {
  const { t, i18n } = useTranslation("common");
  const theme = useTheme();

  /** Declared columns first, then anything the data carries beyond them. */
  const names = useMemo(() => {
    const declared = columns
      .map((column) => column.name)
      .filter((name) => !!name && !STRUCTURAL.has(name));
    const seen = new Set(declared);
    const extra: string[] = [];
    for (const feature of features) {
      for (const key of Object.keys(feature.properties ?? {})) {
        if (!seen.has(key)) {
          seen.add(key);
          extra.push(key);
        }
      }
    }
    return [...declared, ...extra];
  }, [columns, features]);

  const fields = useMemo<LayerField[]>(
    () =>
      names.map((name) => ({
        name,
        type: columns.find((column) => column.name === name)?.type ?? "text",
      })),
    [names, columns]
  );

  const rows = useMemo(
    () =>
      features.map(
        (feature) =>
          formatFeatureProperties({
            properties: (feature.properties ?? {}) as Record<string, unknown>,
            layerFields: fields,
            lang: i18n.language,
          }).byColumn
      ),
    [features, fields, i18n.language]
  );

  if (!names.length || !rows.length) return null;

  const cellSx = {
    px: 3,
    py: 2,
    fontSize: 12.5,
    whiteSpace: "nowrap",
    maxWidth: 280,
    overflow: "hidden",
    textOverflow: "ellipsis",
  } as const;

  return (
    <Box>
      <Box
        sx={{
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 2,
          overflow: "auto",
          maxHeight: MAX_HEIGHT,
        }}>
        <Box component="table" sx={{ borderCollapse: "collapse", width: "100%" }}>
          <Box component="thead">
            <Box component="tr">
              {names.map((name) => (
                <Box
                  component="th"
                  key={name}
                  sx={{
                    ...cellSx,
                    // The header stays put while the rows scroll under it —
                    // a 100-row sample is otherwise unreadable past the fold.
                    position: "sticky",
                    top: 0,
                    zIndex: 1,
                    textAlign: "left",
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: 0.4,
                    textTransform: "uppercase",
                    color: theme.palette.text.secondary,
                    backgroundColor: theme.palette.background.paper,
                    borderBottom: `1px solid ${theme.palette.divider}`,
                    fontFamily: "ui-monospace, monospace",
                  }}>
                  {name}
                </Box>
              ))}
            </Box>
          </Box>
          <Box component="tbody">
            {rows.map((row, index) => (
              <Box
                component="tr"
                key={index}
                sx={{
                  "&:nth-of-type(even)": { backgroundColor: theme.palette.action.hover },
                }}>
                {names.map((name) => (
                  <Box component="td" key={name} sx={cellSx} title={row[name] ?? ""}>
                    {row[name] || (
                      <Typography
                        component="span"
                        sx={{ color: theme.palette.text.disabled, fontSize: 12.5 }}>
                        —
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
        {t("catalog_feature_sample_note", { count: rows.length })}
      </Typography>
    </Box>
  );
};

export default CatalogFeatureTable;
