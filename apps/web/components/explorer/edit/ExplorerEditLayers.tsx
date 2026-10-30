/**
 * What editing draws on the map and takes from it, beside the Explorer's own
 * layers (ExplorerMapLayers): the Stop tool's clicks, under a crosshair, and
 * the stop being placed, which can be dragged until it is created (board 18).
 */
import { useTheme } from "@mui/material/styles";
import type { FeatureCollection } from "geojson";
import type { MapLayerMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useState } from "react";
import { Layer, Source, useMap } from "react-map-gl/maplibre";

import { placeStop } from "@/lib/store/explorer/slice";
import { setMapCursor } from "@/lib/store/map/slice";

import { useDragPoint } from "@/hooks/explorer/useDragPoint";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

/** The editing layers, bottom to top: placed above the Explorer's own. */
export const EDIT_DRAW_ORDER = ["explorer-draft-stop-halo", "explorer-draft-stop-dot"];

type LonLat = [number, number];

export function ExplorerEditLayers() {
  const dispatch = useAppDispatch();
  const theme = useTheme();
  const { current: map } = useMap();
  const tool = useAppSelector((s) => s.explorer.edit.tool);
  const draft = useAppSelector((s) => s.explorer.edit.draft);
  const placing = draft?.kind === "stop-new" ? draft : null;
  // Where the point being dragged is, before it is let go.
  const [dragAt, setDragAt] = useState<LonLat | null>(null);

  // The Stop tool: a crosshair, and a click places the stop there. The
  // map's cursor is the measure tool's way too: given back on leaving.
  useEffect(() => {
    if (!map || tool !== "stop") return;
    dispatch(setMapCursor("crosshair"));
    const onClick = (e: MapLayerMouseEvent) => dispatch(placeStop({ lon: e.lngLat.lng, lat: e.lngLat.lat }));
    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
      dispatch(setMapCursor(undefined));
    };
  }, [map, tool, dispatch]);

  // A stop being placed is dragged again where it now is.
  useDragPoint(
    map?.getMap(),
    ["explorer-draft-stop-dot", "explorer-draft-stop-halo"],
    !!placing,
    setDragAt,
    ([lon, lat]) => dispatch(placeStop({ lon, lat }))
  );

  const at = useMemo<LonLat | null>(
    () => dragAt ?? (placing ? [placing.lon, placing.lat] : null),
    [dragAt, placing]
  );
  const point = useMemo<FeatureCollection>(
    () =>
      at
        ? {
            type: "FeatureCollection",
            features: [{ type: "Feature", geometry: { type: "Point", coordinates: at }, properties: {} }],
          }
        : EMPTY,
    [at]
  );

  return (
    <>
      <Source key="explorer-draft-stop" id="explorer-draft-stop" type="geojson" data={point}>
        {/* As a picked stop, its halo ringed: not in the network yet. */}
        <Layer
          id="explorer-draft-stop-halo"
          type="circle"
          paint={{
            "circle-radius": 16,
            "circle-color": theme.palette.primary.main,
            "circle-opacity": 0.14,
            "circle-stroke-color": theme.palette.primary.main,
            "circle-stroke-width": 1.5,
            "circle-stroke-opacity": 0.6,
          }}
        />
        <Layer
          id="explorer-draft-stop-dot"
          type="circle"
          paint={{
            "circle-radius": 6,
            "circle-color": "#FFFFFF",
            "circle-stroke-color": theme.palette.primary.main,
            "circle-stroke-width": 3,
          }}
        />
      </Source>
    </>
  );
}
