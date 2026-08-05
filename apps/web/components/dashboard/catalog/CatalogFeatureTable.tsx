"use client";

import { Box, Typography, useTheme } from "@mui/material";
import { type Theme, emphasize } from "@mui/material/styles";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { DatasetCollectionItems } from "@/lib/validations/layer";
import type { CatalogColumn } from "@/lib/validations/catalog";

import FeatureTable, { type FeatureTableField } from "@/components/common/FeatureTable";

/**
 * The dataset's actual rows — the preview sample, one line per feature.
 *
 * The Data tab used to show only the column dictionary, which answers "what
 * fields exist" but not the question people open a dataset to ask: what does a
 * record look like. The preview already carries up to 100 features with their
 * attributes, so the rows cost nothing beyond rendering them.
 *
 * The table itself is the app's own `FeatureTable` — the one the dataset modal,
 * the dashboard widget and the workflows data panel use. It is presentational and
 * documented for callers that synthesise rows rather than page them from the API,
 * which is exactly a catalog dataset: it has no layer to query yet. So a value
 * reads here the way it reads in every other GOAT table, and column resizing or
 * cell formatting improvements arrive here for free.
 *
 * What stays local is the part that is about the catalog rather than about tables:
 * which columns to show, and in which order.
 */

/**
 * Columns that are the feature's shape rather than its attributes. The preview
 * strips them from `properties` — the same set `catalog.services.preview` calls
 * non-property columns — so a table listing them would show a blank per row and
 * read as missing data.
 */
const STRUCTURAL = new Set(["geometry", "geom", "bbox"]);

/** Tall enough to read a dozen records in, short enough to leave the dictionary
 * below it reachable. */
const MAX_HEIGHT = 420;

/**
 * The header's surface: a touch lighter than the card, the same lift the data
 * table in map mode gives its own sticky header. Named because two things need
 * it — the header cells, and the scrollbar gutter beside them.
 */
const HEADER_BG = (theme: Theme) => emphasize(theme.palette.background.paper, 0.03);

const CatalogFeatureTable = ({
  features,
  columns,
  truncated,
}: {
  features: GeoJSON.Feature[];
  columns: CatalogColumn[];
  /**
   * Whether the dataset holds more than these features — the preview's own
   * `goat:truncated`, rather than a guess from the row count. A dataset with 75
   * rows is shown in full, and telling its reader the view was "limited" would be
   * false.
   */
  truncated?: boolean;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  /**
   * How tall the header is, so the strip beside it can be painted to match — see
   * the band on the scrolling box. Measured rather than assumed: the height
   * depends on the theme's metrics and on whether a long column name wraps.
   */
  const scrollBox = useRef<HTMLDivElement | null>(null);
  const [headHeight, setHeadHeight] = useState(0);
  useEffect(() => {
    const head = scrollBox.current?.querySelector("thead");
    if (!head) return;
    const measure = () => setHeadHeight(head.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(head);
    return () => observer.disconnect();
  }, [columns, features]);

  /** Declared columns first, then anything the data carries beyond them. */
  const fields = useMemo<FeatureTableField[]>(() => {
    const declared = columns.filter(
      (column) => !!column.name && !STRUCTURAL.has(column.name)
    );
    const seen = new Set(declared.map((column) => column.name));
    const extra: FeatureTableField[] = [];
    for (const feature of features) {
      for (const key of Object.keys(feature.properties ?? {})) {
        if (!seen.has(key)) {
          seen.add(key);
          // A value nobody declared is still a value.
          extra.push({ name: key, type: "string" });
        }
      }
    }
    return [
      ...declared.map((column) => ({ name: column.name, type: column.type ?? "string" })),
      ...extra,
    ];
  }, [columns, features]);

  /**
   * The sample as the table's own page shape. Only `features[].properties` is
   * read for rendering; the counts describe the sample honestly, and the
   * remaining members belong to an OGC Features page this is not — a preview has
   * no links to follow and no title of its own.
   */
  const data = useMemo<DatasetCollectionItems>(
    () => ({
      type: "FeatureCollection",
      title: "",
      links: [],
      numberMatched: features.length,
      numberReturned: features.length,
      features: features.map((feature, index) => ({
        type: "Feature",
        // Positional: preview features carry no id, and the table only needs a
        // stable key per row.
        id: index,
        properties: (feature.properties ?? {}) as Record<string, unknown>,
      })),
    }),
    [features]
  );

  if (!fields.length || !features.length) return null;

  return (
    <Box
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 2,
        overflow: "hidden",
      }}>
      <Box
        ref={scrollBox}
        sx={{
          overflow: "auto",
          maxHeight: MAX_HEIGHT,
          /**
           * The platform's own scrollbar, deliberately unstyled.
           *
           * Starting the thumb below the sticky header needs the track inset with
           * `::-webkit-scrollbar-track`, and touching any of those pseudo-elements
           * makes Chrome swap the platform bar for a custom one: always drawn,
           * always holding its gutter, and defaulting its track and corner to
           * white whatever the theme says. That trade is worse than the thing it
           * fixes. A scrollbar spanning the header is a small oddity; a permanent
           * white bar down a dark table is not.
           *
           * The one part worth keeping is the band: the gutter sits outside the
           * table's box, so the card shows through beside the header as a notch.
           * Painting the box's top strip in the header's colour closes it, and the
           * gradient is attached to the box rather than the content, so it stays
           * put while the rows scroll under it.
           */
          backgroundImage: `linear-gradient(${HEADER_BG(theme)} 0 ${headHeight}px, transparent ${headHeight}px)`,
        }}>
        {/* Dressed like the data table in map mode, which is where people meet a
            table of features in this product:
            - `bordered` for the column dividers. A sample runs to 40 columns and
              scrolls sideways, and without them the eye loses the column it was
              following. (Map mode is a separate component, but its rule is the
              one this variant applies.)
            - a header a touch lighter than the card, the same lift map mode gives
              its own. The default is the *page* background, which is darker than
              this card in the dark theme and read as a band laid over the table. */}
        <FeatureTable
          fields={fields}
          data={data}
          variant="bordered"
          headerColor={HEADER_BG(theme)}
        />
      </Box>
      {/* Why the table stops where it does, in the footer of the frame it applies
          to rather than as a sentence underneath it. The count above says how big
          the dataset is; this says how much of it you are looking at — so it is
          only worth saying when the two differ. */}
      {truncated && (
        <Box
          sx={{
            px: 3,
            py: 2,
            borderTop: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.action.hover,
          }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
            <Icon
              iconName={ICON_NAME.TABLE}
              style={{ fontSize: 11 }}
              htmlColor={theme.palette.text.secondary}
            />
            {t("catalog_preview_limited", { count: features.length })}
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default CatalogFeatureTable;
