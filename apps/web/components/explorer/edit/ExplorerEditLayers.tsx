/**
 * What editing draws on the map and takes from it, beside the Explorer's own
 * layers (ExplorerMapLayers):
 *
 * - the Stop tool's clicks, under a crosshair, and the stop being placed,
 *   which can be dragged until it is created (board 18);
 * - with Select, the picked stop dragged to move it (board 23): where it
 *   goes, a dashed line from where it was and how far, and the paths through
 *   it as they would run, dotted in their line's colour, until Apply or Cancel.
 */
import { useTheme } from "@mui/material/styles";
import type { FeatureCollection } from "geojson";
import type { MapLayerMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { Layer, Source, useMap } from "react-map-gl/maplibre";

import { draftPathsStore, previewedStore } from "@/lib/explorer/edit/draftStore";
import { metres } from "@/lib/explorer/edit/ops/geo";
import { mapColor, mapPalette } from "@/lib/explorer/mapPalette";
import { networkStore } from "@/lib/explorer/network";
import { pickedStop, placeStop, setEditDraft } from "@/lib/store/explorer/slice";
import { setMapCursor } from "@/lib/store/map/slice";

import { useDragPoint } from "@/hooks/explorer/useDragPoint";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

/** The editing layers, bottom to top: placed above the Explorer's own. */
export const EDIT_DRAW_ORDER = [
  "explorer-draft-paths-old",
  "explorer-draft-paths",
  "explorer-draft-move",
  "explorer-draft-from",
  "explorer-draft-stop-halo",
  "explorer-draft-stop-dot",
  "explorer-draft-move-label",
];

type LonLat = [number, number];

/** The dot a new path is drawn with, one every DOT_SPACING px along it: a
 * signed distance field, so each path tints it with its line's colour. A row
 * of icons, not a dash pattern: the map rescales a pattern between zoom
 * levels, and its dots came out uneven. */
const DOT = "explorer-draft-dot";
const DOT_SPACING = 9;
function dotImage(): { image: ImageData; options: object } {
  // At twice the CSS size: a dot 5 px across. The edge at 0.75, falling by
  // 1/8 a pixel outward, as the map reads a distance field.
  const size = 24;
  const r = 5;
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const out = Math.hypot(x + 0.5 - size / 2, y + 0.5 - size / 2) - r;
      const k = (y * size + x) * 4;
      data[k] = data[k + 1] = data[k + 2] = 255;
      data[k + 3] = Math.max(0, Math.min(255, Math.round((0.75 - out / 8) * 255)));
    }
  return { image: new ImageData(data, size, size), options: { pixelRatio: 2, sdf: true } };
}

export function ExplorerEditLayers() {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const theme = useTheme();
  const { current: map } = useMap();
  const editor = useAppSelector((s) => s.explorer.edit.enabled);
  const tool = useAppSelector((s) => s.explorer.edit.tool);
  const draft = useAppSelector((s) => s.explorer.edit.draft);
  const picked = useAppSelector((s) => (s.explorer.active ? pickedStop(s.explorer) : null));
  const network = useSyncExternalStore(
    networkStore.subscribe,
    networkStore.getSnapshot,
    networkStore.getSnapshot
  );
  const paths = useSyncExternalStore(
    draftPathsStore.subscribe,
    draftPathsStore.getSnapshot,
    draftPathsStore.getSnapshot
  );
  const placing = draft?.kind === "stop-new" ? draft : null;
  const moving = draft?.kind === "stop-move" ? draft : null;
  // Where the point being dragged is, before it is let go.
  const [dragAt, setDragAt] = useState<LonLat | null>(null);

  // The picked stop where the network has it: a stop of its own (not a
  // station), which an editor can drag with Select.
  const pickedAt = useMemo<LonLat | null>(() => {
    if (!picked) return null;
    const f = network.stops.features.find((x) => x.properties.stop_idx === picked.stop_idx);
    return f ? (f.geometry.coordinates as LonLat) : null;
  }, [picked, network.stops]);

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

  // The dot of the new paths, there before a path is: asked for only when
  // the map first draws one, the dots came a moment after the path's old
  // parts. Drawn again when the map asks, for a new style that drops it.
  useEffect(() => {
    if (!map) return;
    const raw = map.getMap();
    const add = () => {
      if (raw.hasImage(DOT)) return;
      const { image, options } = dotImage();
      raw.addImage(DOT, image, options);
    };
    const onMissing = (e: { id: string }) => {
      if (e.id === DOT) add();
    };
    add();
    raw.on("styleimagemissing", onMissing);
    return () => {
      raw.off("styleimagemissing", onMissing);
    };
  }, [map]);

  // With Select, the picked stop is dragged to move it.
  useDragPoint(
    map?.getMap(),
    ["explorer-picked-stop-dot", "explorer-picked-stop-halo"],
    editor && tool === "select" && !!picked && !!pickedAt && !moving,
    setDragAt,
    ([lon, lat]) =>
      picked && dispatch(setEditDraft({ kind: "stop-move", stop_idx: picked.stop_idx, lon, lat }))
  );
  // A stop being placed or moved is dragged again where it now is.
  useDragPoint(
    map?.getMap(),
    ["explorer-draft-stop-dot", "explorer-draft-stop-halo"],
    !!placing || !!moving,
    setDragAt,
    ([lon, lat]) => {
      if (placing) dispatch(placeStop({ lon, lat }));
      else if (moving) dispatch(setEditDraft({ ...moving, lon, lat }));
    }
  );

  const at = useMemo<LonLat | null>(
    () => dragAt ?? (placing ? [placing.lon, placing.lat] : moving ? [moving.lon, moving.lat] : null),
    [dragAt, placing, moving]
  );
  // Moving: from where it was, while it is dragged or waits for Apply.
  const from = moving || (dragAt && !placing) ? pickedAt : null;
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
  const move = useMemo<FeatureCollection>(
    () =>
      at && from
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                geometry: { type: "LineString", coordinates: [from, at] },
                properties: {},
              },
              {
                type: "Feature",
                geometry: { type: "Point", coordinates: at },
                properties: { label: t("explorer_moved_m", { metres: Math.round(metres(from, at)) }) },
              },
            ],
          }
        : EMPTY,
    [at, from, t]
  );
  // Moving, the stop is where it goes: where it was is a hollow ring, the
  // picked stop's own marker set aside meanwhile (board 23).
  useEffect(() => {
    const raw = map?.getMap();
    if (!raw) return;
    const visibility = from ? "none" : "visible";
    for (const id of ["explorer-picked-stop-halo", "explorer-picked-stop-dot"])
      if (raw.getLayer(id)) raw.setLayoutProperty(id, "visibility", visibility);
  }, [map, from]);
  const fromPoint = useMemo<FeatureCollection>(
    () =>
      from
        ? {
            type: "FeatureCollection",
            features: [{ type: "Feature", geometry: { type: "Point", coordinates: from }, properties: {} }],
          }
        : EMPTY,
    [from]
  );

  // The paths as they would run, once the drop is built (not while
  // dragging): dotted in their line's colour, over the path each replaces,
  // drawn here in the network's stead and faint where it is drawn anew.
  // A stop being added to a line shows its paths as a moved one does.
  const shown = (!!moving || draft?.kind === "line-stop-add") && !dragAt;
  // In the colours the network is drawn in for the basemap under it: a dark
  // line lifted on a dark one, as ExplorerMapLayers draws it.
  const basemap = useAppSelector((s) => s.map.activeBasemap?.value);
  const painted = useMemo(() => {
    const palette = mapPalette(basemap);
    return {
      ...paths,
      features: paths.features.map((f) => ({
        ...f,
        properties: { ...f.properties, color: mapColor(f.properties.color, palette) },
      })),
    };
  }, [paths, basemap]);
  const preview = shown ? painted : EMPTY;
  useEffect(() => {
    previewedStore.set(shown && paths.features.length ? draftPathsStore.replaces() : null);
  }, [shown, paths]);
  useEffect(() => () => previewedStore.set(null), []);

  return (
    <>
      <Source key="explorer-draft-paths" id="explorer-draft-paths" type="geojson" data={preview}>
        {/* The old path as the network draws it, faint where it is replaced. */}
        <Layer
          id="explorer-draft-paths-old"
          type="line"
          filter={["!=", ["get", "kind"], "new"]}
          paint={{
            "line-color": ["get", "color"],
            "line-opacity": ["case", ["==", ["get", "kind"], "replaced"], 0.25, 0.9],
            "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 14, 3.5],
          }}
        />
        <Layer
          id="explorer-draft-paths"
          type="symbol"
          filter={["==", ["get", "kind"], "new"]}
          layout={{
            "symbol-placement": "line",
            "symbol-spacing": DOT_SPACING,
            "icon-image": DOT,
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
            "icon-padding": 0,
            "icon-rotation-alignment": "map",
          }}
          paint={{ "icon-color": ["get", "color"] }}
        />
      </Source>
      <Source key="explorer-draft-move" id="explorer-draft-move" type="geojson" data={move}>
        <Layer
          id="explorer-draft-move"
          type="line"
          filter={["==", ["geometry-type"], "LineString"]}
          paint={{
            "line-color": theme.palette.text.secondary,
            "line-width": 1.5,
            "line-dasharray": [2, 2],
          }}
        />
        <Layer
          id="explorer-draft-move-label"
          type="symbol"
          filter={["==", ["geometry-type"], "Point"]}
          layout={{
            "text-field": ["get", "label"],
            "text-font": ["Roboto Bold"],
            "text-size": 11.5,
            "text-offset": [0, 1.6],
            "text-anchor": "top",
            "text-allow-overlap": true,
          }}
          paint={{
            "text-color": theme.palette.text.primary,
            "text-halo-color": theme.palette.background.paper,
            "text-halo-width": 1.5,
          }}
        />
      </Source>
      <Source key="explorer-draft-from" id="explorer-draft-from" type="geojson" data={fromPoint}>
        <Layer
          id="explorer-draft-from"
          type="circle"
          paint={{
            "circle-radius": 5,
            "circle-color": theme.palette.background.paper,
            "circle-opacity": 0.6,
            "circle-stroke-color": theme.palette.text.secondary,
            "circle-stroke-width": 1.5,
          }}
        />
      </Source>
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
