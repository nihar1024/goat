import { Alert, Box, Skeleton } from "@mui/material";
import bboxOf from "@turf/bbox";
import "maplibre-gl/dist/maplibre-gl.css";
import { useMemo } from "react";
import { Layer as MapLayer, Map as MapLibre, Source } from "react-map-gl/maplibre";
import { useTranslation } from "react-i18next";

import { useCatalogPreview } from "@/lib/api/catalog";

import { useCatalogBasemapStyle } from "@/hooks/catalog/useCatalogBasemapStyle";
import type { CatalogItem } from "@/lib/validations/catalog";

/**
 * Where the dataset is, and — where the deployment allows it — what it contains.
 *
 * Two levels of detail, because only one of them is always available:
 *
 * - The **footprint** comes from the item's own `geometry`/`bbox`, which the
 *   catalog always serves. It answers "does this cover my area".
 * - A bounded **feature sample** comes from `/stac/items/{id}/preview`, which
 *   reads the published GeoParquet and 404s when no catalog bucket is
 *   configured. Treated as "no preview here" rather than an error, per that
 *   endpoint's contract.
 *
 * Neither renders the dataset as a GOAT layer: catalog data lives in DuckLake
 * only after a project adds it (promote-on-use), so tiles do not exist yet.
 *
 * No caption either way. It used to carry a permanent "showing the extent" strip,
 * which read as a warning rather than a label — and in the dark theme a light
 * banner across the bottom of the map fought everything around it. A footprint is
 * self-evidently a footprint once you look at it, and when the sample is available
 * the map simply shows the data.
 */

const FOOTPRINT_COLOR = "#2278CF";

const CatalogFootprintMap = ({
  item,
  /**
   * Fills its container instead of standing at a fixed height. The prototype
   * shows the map inline in the Summary column, where it stretches to whatever
   * the description leaves — so the height belongs to the caller there.
   */
  fill,
}: {
  item: CatalogItem;
  fill?: boolean;
}) => {
  const { t } = useTranslation("common");
  const basemapStyle = useCatalogBasemapStyle();
  const { preview, isLoading } = useCatalogPreview(item.id);

  const footprint = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!item.geometry) return null;
    return {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: item.geometry, properties: {} }],
    };
  }, [item.geometry]);

  const sample = preview?.features?.length
    ? ({ type: "FeatureCollection", features: preview.features } as GeoJSON.FeatureCollection)
    : null;

  const shown = sample ?? footprint;

  const initialViewState = useMemo(() => {
    const box = item.bbox ?? (shown ? (bboxOf(shown) as number[]) : null);
    if (!box || box.length < 4) return { longitude: 10, latitude: 51, zoom: 3 };
    return {
      bounds: [box[0], box[1], box[2], box[3]] as [number, number, number, number],
      fitBoundsOptions: { padding: 40 },
    };
  }, [item.bbox, shown]);

  if (!shown) {
    return <Alert severity="info">{t("catalog_no_geometry")}</Alert>;
  }


  return (
    <Box sx={fill ? { position: "absolute", inset: 0 } : undefined}>
      {isLoading && <Skeleton variant="rectangular" height={4} sx={{ mb: 1 }} />}
      <Box
        sx={
          fill
            ? { position: "absolute", inset: 0 }
            : { height: 420, borderRadius: 1, overflow: "hidden" }
        }>
        <MapLibre
          initialViewState={initialViewState}
          style={{ width: "100%", height: "100%" }}
          mapStyle={basemapStyle}>
          <Source id="catalog-geometry" type="geojson" data={shown}>
            <MapLayer
              id="catalog-geometry-fill"
              type="fill"
              paint={{ "fill-color": FOOTPRINT_COLOR, "fill-opacity": sample ? 0.35 : 0.12 }}
              filter={["==", ["geometry-type"], "Polygon"]}
            />
            <MapLayer
              id="catalog-geometry-line"
              type="line"
              paint={{ "line-color": FOOTPRINT_COLOR, "line-width": 1.5 }}
            />
            <MapLayer
              id="catalog-geometry-point"
              type="circle"
              paint={{ "circle-color": FOOTPRINT_COLOR, "circle-radius": 3 }}
              filter={["==", ["geometry-type"], "Point"]}
            />
          </Source>
        </MapLibre>
      </Box>
    </Box>
  );
};

export default CatalogFootprintMap;
