import { Box } from "@mui/material";

import AttributionControl from "@/components/map/controls/Attribution";

/**
 * The credit strip for the catalog's maps, in place of maplibre's own control.
 *
 * Attribution is not optional here: the basemap's tiles come from MapTiler and its
 * data from OpenStreetMap, and both require a visible credit. What is optional is
 * the "MapLibre" wordmark maplibre's default control adds — that credits the
 * rendering library, not the data — so this uses the app's own control instead,
 * which reads the credits off the style's sources and reads the same on every GOAT
 * map ("Made with GOAT. Data from …", with the full list a click away).
 *
 * Flush to the bottom-right. Callers with something in the bottom-left corner — a
 * legend — cap the width so the two never meet; the credit then clips to its own
 * "more" link, which opens the full list. Must be rendered inside the map: the
 * control resolves the map it is mounted in to read those sources.
 */
const CatalogMapAttribution = ({
  /** Share of the map's width the strip may take. Full width by default. */
  maxWidth = "100%",
}: {
  maxWidth?: string;
}) => (
  <Box
    // Measured by hosts that place something above it — see the preview map's
    // pinned panel, which stops short of this strip.
    data-catalog-attribution
    sx={{
      position: "absolute",
      right: 0,
      bottom: 0,
      maxWidth,
      display: "flex",
      justifyContent: "flex-end",
      // Both needed for the cap to bite: a flex item will not shrink below its
      // content without `minWidth: 0`, so the strip would otherwise overhang to
      // the left of this box — clipped at its start, with no "more" link, since
      // the text inside was never the thing being cut.
      overflow: "hidden",
      "& > *": { minWidth: 0 },
    }}>
    <AttributionControl />
  </Box>
);

export default CatalogMapAttribution;
