import type { FeatureLayerLineProperties, Layer } from "@/lib/validations/layer";
import type { ProjectLayer } from "@/lib/validations/project";

import { getMapboxStyleColor } from "@/lib/transformers/layer";
import { ARROW_SDF_SOURCE_SIZE } from "@/lib/utils/map/registerSpriteImages";

export type StrokePattern = "solid" | "dashed" | "dotted" | "dash_dot";
export type StrokeDashDensity = "tight" | "normal" | "loose";

const DASH_TABLE = {
  dashed: {
    tight: [2, 1],
    normal: [3, 2],
    loose: [4, 4],
  },
  dotted: {
    tight: [0.5, 1],
    normal: [0.5, 2],
    loose: [0.5, 4],
  },
  dash_dot: {
    tight: [3, 1, 0.5, 1],
    normal: [3, 2, 0.5, 2],
    loose: [4, 4, 0.5, 4],
  },
} as const satisfies Record<Exclude<StrokePattern, "solid">, Record<StrokeDashDensity, readonly number[]>>;

export function resolveLineDashArray(
  pattern: StrokePattern,
  density: StrokeDashDensity
): readonly number[] | undefined {
  if (pattern === "solid") return undefined;
  return DASH_TABLE[pattern][density];
}

export type DecorationType = "none" | "arrow";
export type DecorationDirection = "forward" | "backward" | "both";
export type DecorationPlacement = "repeat" | "start" | "end" | "start_and_end" | "center";

export interface LineDecorationLayerSpec {
  id: string;
  type: "symbol";
  sourceLayer: "default" | "default_decoration";
  layout: Record<string, unknown>;
  paint: Record<string, unknown>;
}

export function transformToLineDecorationLayers(
  data: ProjectLayer | Layer
): LineDecorationLayerSpec[] {
  const lineProps = data.properties as FeatureLayerLineProperties;
  // `??` fallbacks: legacy layers persisted before these fields existed
  // won't have them in the dict; defaults match the Zod schema.
  const decorationType = lineProps.decoration_type ?? "none";
  if (decorationType === "none") return [];

  const direction = lineProps.decoration_direction ?? "forward";
  const spacing = lineProps.decoration_spacing ?? 200;
  // `decoration_size` is the user-facing target arrow size in screen pixels.
  // Convert to MapLibre's `icon-size` (a multiplier on the source raster).
  const targetPx = lineProps.decoration_size ?? 32;
  const size = targetPx / ARROW_SDF_SOURCE_SIZE;
  const allowOverlap = lineProps.decoration_allow_overlap ?? true;
  const visibility = lineProps.visibility ? "visible" : "none";

  const placement = (lineProps.decoration_placement ?? "repeat") as DecorationPlacement;

  if (placement !== "repeat") {
    return buildPointDecorations(data, direction, size, allowOverlap, visibility);
  }

  // repeat-placement: symbol repeated along the line geometry
  const baseLayout: Record<string, unknown> = {
    "symbol-placement": "line",
    "icon-image": "arrow-sdf",
    "icon-rotation-alignment": "map",
    "icon-size": size,
    "symbol-spacing": spacing,
    // When true, every arrow renders even where it would collide with another
    // symbol — and doesn't block other symbols. When false, MapLibre's
    // collision detector culls overlapping arrows (cleaner but loses arrows
    // at low zoom / in dense areas).
    "icon-allow-overlap": allowOverlap,
    "icon-ignore-placement": allowOverlap,
    visibility,
  };
  const basePaint = {
    "icon-color": getMapboxStyleColor(data, "stroke_color"),
  };

  const layers: LineDecorationLayerSpec[] = [];
  if (direction === "forward" || direction === "both") {
    layers.push({
      id: `${data.id}-deco-fwd`,
      type: "symbol",
      sourceLayer: "default",
      layout: { ...baseLayout, "icon-rotate": 0 },
      paint: { ...basePaint },
    });
  }
  if (direction === "backward" || direction === "both") {
    layers.push({
      id: `${data.id}-deco-bwd`,
      type: "symbol",
      sourceLayer: "default",
      layout: { ...baseLayout, "icon-rotate": 180 },
      paint: { ...basePaint },
    });
  }
  return layers;
}

function buildPointDecorations(
  data: ProjectLayer | Layer,
  direction: DecorationDirection,
  size: number,
  allowOverlap: boolean,
  visibility: "visible" | "none",
): LineDecorationLayerSpec[] {
  const baseLayout = {
    "symbol-placement": "point",
    "icon-image": "arrow-sdf",
    "icon-rotation-alignment": "map",
    "icon-size": size,
    "icon-allow-overlap": allowOverlap,
    "icon-ignore-placement": allowOverlap,
    visibility,
  };
  const basePaint = {
    "icon-color": getMapboxStyleColor(data, "stroke_color"),
  };

  // Bearing math: arrow SVG points east at 0°. Backend bearings are degrees
  // clockwise from north. So forward = bearing - 90; backward = bearing + 90.
  const forwardRotate = ["-", ["get", "bearing"], 90];
  const backwardRotate = ["+", ["get", "bearing"], 90];

  const layers: LineDecorationLayerSpec[] = [];
  if (direction === "forward" || direction === "both") {
    layers.push({
      id: `${data.id}-deco-fwd-pt`,
      type: "symbol",
      sourceLayer: "default_decoration",
      layout: { ...baseLayout, "icon-rotate": forwardRotate },
      paint: { ...basePaint },
    });
  }
  if (direction === "backward" || direction === "both") {
    layers.push({
      id: `${data.id}-deco-bwd-pt`,
      type: "symbol",
      sourceLayer: "default_decoration",
      layout: { ...baseLayout, "icon-rotate": backwardRotate },
      paint: { ...basePaint },
    });
  }
  return layers;
}
