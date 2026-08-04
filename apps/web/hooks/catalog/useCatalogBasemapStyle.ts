import { useTheme } from "@mui/material";

import { BASEMAPS } from "@/lib/constants/basemaps";

/**
 * The basemap style matching the current theme.
 *
 * The catalog's three maps — the detail footprint, the spatial-filter tool and the
 * filter panel's preview — were pinned to `dataviz-light`, so in the dark theme
 * each was a bright rectangle in a dark page. The app already ships both styles
 * (`lib/constants/basemaps`); this just picks the one the palette is in.
 */
export const useCatalogBasemapStyle = (): string | undefined => {
  const theme = useTheme();
  const value = theme.palette.mode === "dark" ? "dark" : "light";
  return BASEMAPS.find((basemap) => basemap.value === value)?.url;
};
