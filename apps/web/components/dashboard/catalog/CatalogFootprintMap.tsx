import { Alert, Box, Paper, Skeleton, useTheme } from "@mui/material";
import bboxOf from "@turf/bbox";
import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { MapGeoJSONFeature, MapLayerMouseEvent } from "react-map-gl/maplibre";
import { Layer as MapLayer, Map as MapLibre, Source } from "react-map-gl/maplibre";

import { useCatalogPreview, useCatalogStyle } from "@/lib/api/catalog";
import { catalogPaint } from "@/lib/catalog/style";
import { getHightlightStyleSpec } from "@/lib/transformers/layer";
import type { CatalogItem } from "@/lib/validations/catalog";
import type { PopupProperties } from "@/lib/validations/layer";

import { useCatalogBasemapStyle } from "@/hooks/catalog/useCatalogBasemapStyle";

import CatalogMapAttribution from "@/components/dashboard/catalog/CatalogMapAttribution";
import { LayerLegendPanel } from "@/components/map/panels/layer/legend/LayerLegend";
import type { LayerField } from "@/components/map/popover/formatFeatureProperties";
import { MapFeaturePopover } from "@/components/map/popover/MapFeaturePopover";

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
 * **A sample is drawn, explained and inspected with the app's own components.**
 * The style the harvester publishes has the shape a GOAT layer carries, and it is
 * the same style promote applies when the dataset becomes a layer — so the paint
 * comes from `transformToMapboxLayerStyleSpec`, the legend is the Layers panel's
 * `LayerLegendPanel`, and a hovered or clicked feature opens `MapFeaturePopover`
 * on the same hover-previews/click-pins terms the project map uses. A preview
 * with its own versions of those would drift from the map it exists to predict.
 *
 * The footprint case keeps a neutral accent and none of that furniture: colouring
 * a bounding box in the dataset's palette, or hanging a legend off it, would imply
 * you were looking at the data rather than at its outline.
 */

const FOOTPRINT_COLOR = "#2278CF";

/**
 * Room kept clear for the credit strip, which sits in the same corner the panel is
 * pinned to. A starting guess only, used until the strip has rendered — the real
 * value is measured off it, since its height depends on the theme's caption size.
 */
const ATTRIBUTION_ROOM = 24;

/**
 * The gap `PopupFixedHost` leaves between the panel and the map's edges. Repeated
 * below the panel so the space above the attribution matches the space above the
 * panel, instead of the panel stopping just short of the credit line.
 */
const EDGE_GAP = 12;

type PickedFeature = {
  lngLat: { lng: number; lat: number };
  properties: Record<string, unknown>;
  /** The queried feature, which the shared highlight spec reads id + paint off. */
  feature: MapGeoJSONFeature;
};

const STYLED_LAYER = "catalog-geometry-styled";
const PLAIN_LAYERS = [
  "catalog-geometry-fill",
  "catalog-geometry-line",
  "catalog-geometry-point",
];

const CatalogFootprintMap = ({
  item,
  /**
   * Fills its container instead of standing at a fixed height. The prototype
   * shows the map inline in the Summary column, where the caller owns the height.
   */
  fill,
}: {
  item: CatalogItem;
  fill?: boolean;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const basemapStyle = useCatalogBasemapStyle();
  const { preview, isLoading } = useCatalogPreview(item.id);

  const footprint = useMemo<GeoJSON.FeatureCollection | null>(() => {
    if (!item.geometry) return null;
    return {
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: item.geometry, properties: {} }],
    };
  }, [item.geometry]);

  const sample = useMemo<GeoJSON.FeatureCollection | null>(
    () =>
      preview?.features?.length
        ? { type: "FeatureCollection", features: preview.features }
        : null,
    [preview]
  );
  const shown = sample ?? footprint;

  // Only worth fetching a style when there is data to draw with it.
  const { style } = useCatalogStyle(item.assets?.style?.href, !!sample);
  const geometryType = item.properties["goat:geometryType"] ?? undefined;
  const styled = catalogPaint(style, geometryType);
  /** The dataset's own rendering, and some of its data to draw with it. */
  const styledSample = !!sample && !!styled && !!geometryType;

  /**
   * Field definitions for the popup, from what the dataset published.
   *
   * A promoted layer's popup reads these from core; a catalog dataset has no
   * layer yet, so `table:columns` stands in — same names, same types, so the same
   * formatting applies.
   */
  const fields = useMemo<LayerField[]>(
    () =>
      (item.properties["table:columns"] ?? []).map((column) => ({
        name: column.name,
        type: column.type ?? "text",
      })),
    [item.properties]
  );

  /**
   * The map's rendered height, and how much of its bottom the attribution takes.
   *
   * Both measured rather than assumed. The height, because the caller sets it
   * (460px on a desktop card, 320 on a phone) and a fixed guess would leave dead
   * space on one and overflow the other. The credit strip, because its height comes
   * from the theme's caption metrics rather than from anything stated here.
   */
  const mapBox = useRef<HTMLDivElement | null>(null);
  const [panelHeight, setPanelHeight] = useState(420);
  const [attributionRoom, setAttributionRoom] = useState(ATTRIBUTION_ROOM);
  const measure = useCallback(() => {
    const node = mapBox.current;
    if (!node) return;
    const box = node.getBoundingClientRect();
    setPanelHeight(box.height);
    // Distance from the top of the credit strip to the bottom of the map.
    const attribution = node.querySelector("[data-catalog-attribution]");
    if (!attribution) return;
    const room = box.bottom - attribution.getBoundingClientRect().top;
    if (room > 0 && room < box.height) setAttributionRoom(room);
  }, []);
  useEffect(() => {
    const node = mapBox.current;
    if (!node) return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(node);
    return () => observer.disconnect();
  }, [measure]);

  /**
   * A popup configuration for a dataset that has none.
   *
   * A project layer's popup is authored by whoever owns the layer. A catalog
   * dataset is nobody's yet, so this is the default a reader wants: every field,
   * as a table, in the order the dataset declares them.
   */
  const popup = useMemo<PopupProperties>(
    () =>
      ({
        enabled: true,
        // The same behaviour the project map gives this value: hover previews
        // (transient), click pins (sticky, and hovers stop changing it). Nothing
        // here reads the field -- `MapViewer` drives it off Redux popup state and
        // project layers, neither of which a catalog dataset has, so this map does
        // its own hit-testing -- but the panel it produces should be described in
        // the app's own vocabulary rather than a private one.
        trigger: "click_and_hover",
        mode: "simple",
        blocks: [
          {
            id: "catalog-fields",
            type: "fieldList",
            layout: "table",
            attributes: fields.map((field) => ({
              name: field.name,
              type: field.type === "number" ? "number" : "string",
            })),
            collapse_after: null,
          },
        ],
        html: "",
        // Pinned to a corner rather than anchored to the feature: an in-place
        // popover sized for a full-screen map covers most of a card-sized one,
        // and it moves under the cursor while you are trying to compare features.
        layout: "pinned",
        anchor: "top_right",
        // No header at all: the page title above the map already says which
        // dataset this is, and the panel closes on the next pan or on a click off
        // the features -- so it needs no close control of its own either.
        header: "none",
        width: 300,
        // Fills the map's height, less the host's gap above, the attribution
        // strip below, and the same gap again between the two. Stopping short of
        // the attribution rather than covering it: it names MapTiler and the
        // OpenStreetMap contributors, whose licences require it stay legible.
        max_height: Math.max(160, panelHeight - EDGE_GAP * 2 - attributionRoom),
      }) as unknown as PopupProperties,
    [fields, panelHeight, attributionRoom]
  );

  /**
   * Two ways a feature becomes the one on show, in order of precedence:
   *
   * - **hovered** -- a preview. Reading a map means sweeping it, and asking for a
   *   click per feature turns "what is this band" into a chore.
   * - **picked** -- a click, which pins. Once pinned the panel stops following the
   *   cursor, so the reader can move the mouse to the panel and read, scroll or
   *   select text in it without the content changing underneath them. That is the
   *   thing hover alone cannot do.
   *
   * Pinned wins, and a click off the features unpins -- so one gesture (click)
   * both opens and closes, and nothing needs a close button.
   */
  const [picked, setPicked] = useState<PickedFeature | null>(null);
  const [hovered, setHovered] = useState<PickedFeature | null>(null);
  const active = picked ?? hovered;
  /** Whether the cursor is over a feature, so the pointer means something. */
  const [hovering, setHovering] = useState(false);

  /**
   * The sample feature under a pointer position.
   *
   * Queried with a small **bbox array**, not with `event.point`. Two things go
   * wrong otherwise, and both fail quietly:
   *
   * - `event.point` is a `Point` from a different module instance than the one
   *   MapLibre type-checks against, so it matches no branch and the query returns
   *   nothing at all.
   * - A plain `{x, y}` is not recognised either -- and there the fallback is
   *   *worse than nothing*: the query degrades to the whole viewport and hands
   *   back every rendered feature, so a click anywhere selected whatever happened
   *   to be first. That is the "I click here and it selects something else" bug.
   *
   * A two-point array is unambiguous, needs no class identity, and gives the
   * tolerance hit-testing wants anyway: a 5px reach so a 3px dot or a hairline is
   * clickable rather than pixel-perfect.
   */
  const featureAt = (event: MapLayerMouseEvent) => {
    const wanted = styledSample ? [STYLED_LAYER] : PLAIN_LAYERS;
    // Only layers the style really holds: a pointer crossing the map while the
    // style is still assembling would otherwise ask for a layer that does not
    // exist yet, which MapLibre reports as a console error rather than an empty
    // result. Read from `getStyle()`, not `getLayer()` -- the latter returns
    // nothing through react-map-gl's wrapper, which silently filtered out every
    // layer and made the map unclickable.
    const present = new Set(
      (event.target.getStyle()?.layers ?? []).map((layer) => layer.id)
    );
    const layers = wanted.filter((id) => present.has(id));
    if (!layers.length) return undefined;
    const { x, y } = event.point;
    const box: [[number, number], [number, number]] = [
      [x - 5, y - 5],
      [x + 5, y + 5],
    ];
    return event.target.queryRenderedFeatures(box, { layers }).at(0);
  };

  const asPicked = (event: MapLayerMouseEvent, hit: MapGeoJSONFeature): PickedFeature => ({
    lngLat: { lng: event.lngLat.lng, lat: event.lngLat.lat },
    properties: (hit.properties ?? {}) as Record<string, unknown>,
    feature: hit,
  });

  const onMapClick = (event: MapLayerMouseEvent) => {
    if (!sample) return;
    const hit = featureAt(event);
    // A click on the basemap unpins. Same gesture, both directions -- which is
    // what lets the panel do without a close control.
    setPicked(hit ? asPicked(event, hit) : null);
  };

  const onMapMouseMove = (event: MapLayerMouseEvent) => {
    if (!sample) return;
    const hit = featureAt(event);
    setHovering(!!hit);
    // A pinned panel is the reader's, not the cursor's.
    if (picked) return;
    setHovered((prev) => {
      if (!hit) return prev ? null : prev;
      // Same feature under the cursor: keep the previous object. A mousemove
      // fires per pixel, and a fresh object each time would re-render the whole
      // panel while the reader's eyes are still on the first field.
      if (prev && prev.feature.id === hit.id) return prev;
      return asPicked(event, hit);
    });
  };

  /**
   * Escape dismisses the panel. Redundant with clicking the basemap, on purpose:
   * a panel filling the map's height leaves little basemap to click, and Escape
   * is what a keyboard reader will reach for.
   *
   * It has to drop the preview as well as the pin. The cursor is still wherever
   * it was when the panel was pinned -- usually on the very feature -- so
   * unpinning alone just hands the panel to the hover underneath it and nothing
   * appears to happen. Nothing re-opens until the pointer moves again.
   */
  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setPicked(null);
      setHovered(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

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
        ref={mapBox}
        sx={{
          ...(fill
            ? { position: "absolute", inset: 0 }
            : { height: 420, borderRadius: 1, overflow: "hidden" }),
        }}>
        <MapLibre
          initialViewState={initialViewState}
          style={{ width: "100%", height: "100%" }}
          mapStyle={basemapStyle}
          // GOAT's own strip replaces it, below.
          attributionControl={false}
          cursor={hovering ? "pointer" : "grab"}
          onClick={onMapClick}
          onMouseMove={onMapMouseMove}
          onMouseOut={() => {
            setHovering(false);
            // The preview follows the cursor off the map; a pinned panel stays.
            setHovered(null);
          }}
          // A panned or zoomed map leaves the panel describing a feature the
          // reader can no longer see, and its highlight somewhere off screen, so
          // moving the map drops both the pin and the preview.
          // The attribution control mounts with the map, after the first measure.
          onLoad={measure}
          onMoveStart={() => {
            setPicked(null);
            setHovered(null);
          }}>
          {/* `generateId` so every sampled feature has one: the shared highlight
              spec targets the active feature by id, and preview GeoJSON carries
              none of its own. */}
          <Source id="catalog-geometry" type="geojson" data={shown} generateId>
            {/* Each layer is a direct child of `Source`, which injects the source
                id into the children it can see -- a wrapping fragment hides them
                from it and costs them their source. */}
            {styledSample && (
              <MapLayer
                {...({
                  id: STYLED_LAYER,
                  ...styled,
                  // No geometry-type filter here, unlike the plain layers below:
                  // this layer's type (fill/line/circle) already comes from the
                  // dataset's own declared geometry, so a filter repeating that
                  // declaration guards nothing -- and if the two ever disagreed it
                  // would blank the layer silently rather than mis-draw visibly.
                  // react-map-gl types a layer as the union of every MapLibre
                  // spec, so one assembled at runtime cannot narrow to a member.
                } as React.ComponentProps<typeof MapLayer>)}
              />
            )}
            {!styledSample && (
              <MapLayer
                id="catalog-geometry-fill"
                type="fill"
                paint={{ "fill-color": FOOTPRINT_COLOR, "fill-opacity": sample ? 0.35 : 0.12 }}
                filter={["==", ["geometry-type"], "Polygon"]}
              />
            )}
            {!styledSample && (
              <MapLayer
                id="catalog-geometry-line"
                type="line"
                paint={{ "line-color": FOOTPRINT_COLOR, "line-width": 1.5 }}
              />
            )}
            {!styledSample && (
              <MapLayer
                id="catalog-geometry-point"
                type="circle"
                paint={{ "circle-color": FOOTPRINT_COLOR, "circle-radius": 3 }}
                filter={["==", ["geometry-type"], "Point"]}
              />
            )}

            {/* The same highlight the project map draws on an active feature --
                a line for fills, a disc for points, in the app's highlight
                colour. */}
            {active && !!getHightlightStyleSpec(active.feature) && (
              <MapLayer
                {...({
                  id: "catalog-geometry-highlight",
                  ...getHightlightStyleSpec(active.feature),
                } as React.ComponentProps<typeof MapLayer>)}
              />
            )}
          </Source>

          {active && (
            <Box
              sx={{
                /**
                 * A hover preview must not take the pointer, or it cannot work at
                 * all: pinned to a corner, the panel opens over the very features
                 * being swept, so the canvas receives a `mouseout` the instant it
                 * appears -- which clears the hover, closes the panel, and
                 * flickers once per pixel of movement.
                 *
                 * So: a ghost while previewing, solid once pinned. A pinned panel
                 * is meant to be scrolled and to have its text selected, and by
                 * then the pointer leaving the map means what it says.
                 *
                 * `!important`, and the whole subtree rather than the outer box:
                 * the popover's own host sets `pointer-events: auto` on itself,
                 * and it is as specific as anything reachable from out here.
                 */
                ...(picked
                  ? null
                  : { "&, & *": { pointerEvents: "none !important" } }),
              }}>
              <MapFeaturePopover
                fields={fields}
                popup={popup}
                properties={active.properties}
                lngLat={active.lngLat}
                onClose={() => {
                  setPicked(null);
                  setHovered(null);
                }}
              />
            </Box>
          )}

          {/* Capped: the legend owns the bottom-left of this map. */}
          <CatalogMapAttribution maxWidth={styledSample ? "62%" : "100%"} />
        </MapLibre>

        {/* The dataset's own legend, from the same style its features are drawn
            with, rendered by the panel the Layers panel uses -- so a colour ramp
            reads identically here and in a project. */}
        {styledSample && (
          <Paper
            elevation={0}
            sx={{
              position: "absolute",
              left: 8,
              bottom: 8,
              maxWidth: 280,
              maxHeight: "70%",
              overflowY: "auto",
              px: 2,
              py: 1.5,
              borderRadius: 1.5,
              border: `1px solid ${theme.palette.divider}`,
              backgroundColor: theme.palette.background.paper,
              opacity: 0.96,
            }}>
            {/* Headings kept: they read "Fill color based on: measure", which is
                what turns a column of swatches into an explanation. At default
                size, too — shrinking a legend to fit a corner is how it stops
                being readable. */}
            <LayerLegendPanel
              properties={style as Record<string, unknown>}
              geometryType={geometryType}
            />
          </Paper>
        )}
      </Box>
    </Box>
  );
};

export default CatalogFootprintMap;
