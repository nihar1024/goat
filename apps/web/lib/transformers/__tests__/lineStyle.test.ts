import { describe, expect, it } from "vitest";

import { resolveLineDashArray, transformToLineDecorationLayers } from "../lineStyle";
import { getMapboxStyleColor, transformToMapboxLayerStyleSpec } from "../layer";

function makeLineLayer(properties: Record<string, unknown> = {}) {
  return {
    id: "test-line",
    type: "feature",
    feature_layer_geometry_type: "line",
    properties: {
      visibility: true,
      opacity: 1,
      stroke_width: 2,
      ...properties,
    },
  } as unknown as Parameters<typeof transformToMapboxLayerStyleSpec>[0];
}

describe("resolveLineDashArray", () => {
  it("returns undefined for solid pattern (any density)", () => {
    expect(resolveLineDashArray("solid", "tight")).toBeUndefined();
    expect(resolveLineDashArray("solid", "normal")).toBeUndefined();
    expect(resolveLineDashArray("solid", "loose")).toBeUndefined();
  });

  it("returns canonical dasharrays for dashed", () => {
    expect(resolveLineDashArray("dashed", "tight")).toEqual([2, 1]);
    expect(resolveLineDashArray("dashed", "normal")).toEqual([3, 2]);
    expect(resolveLineDashArray("dashed", "loose")).toEqual([4, 4]);
  });

  it("returns canonical dasharrays for dotted", () => {
    expect(resolveLineDashArray("dotted", "tight")).toEqual([0.5, 1]);
    expect(resolveLineDashArray("dotted", "normal")).toEqual([0.5, 2]);
    expect(resolveLineDashArray("dotted", "loose")).toEqual([0.5, 4]);
  });

  it("returns canonical dasharrays for dash_dot", () => {
    expect(resolveLineDashArray("dash_dot", "tight")).toEqual([3, 1, 0.5, 1]);
    expect(resolveLineDashArray("dash_dot", "normal")).toEqual([3, 2, 0.5, 2]);
    expect(resolveLineDashArray("dash_dot", "loose")).toEqual([4, 4, 0.5, 4]);
  });
});

describe("transformToMapboxLayerStyleSpec — line branch", () => {
  it("omits line-dasharray, line-cap, line-join when defaults / unset", () => {
    const spec = transformToMapboxLayerStyleSpec(makeLineLayer()) as {
      paint: Record<string, unknown>;
      layout: Record<string, unknown>;
    };
    expect(spec.paint["line-dasharray"]).toBeUndefined();
    expect(spec.layout["line-cap"]).toBeUndefined();
    expect(spec.layout["line-join"]).toBeUndefined();
  });

  it("emits line-dasharray for dashed normal", () => {
    const spec = transformToMapboxLayerStyleSpec(
      makeLineLayer({ stroke_pattern: "dashed", stroke_dash_density: "normal" })
    ) as { paint: Record<string, unknown> };
    expect(spec.paint["line-dasharray"]).toEqual([3, 2]);
  });

  it("emits line-cap and line-join when set", () => {
    const spec = transformToMapboxLayerStyleSpec(
      makeLineLayer({ stroke_cap: "round", stroke_join: "round" })
    ) as { layout: Record<string, unknown> };
    expect(spec.layout["line-cap"]).toBe("round");
    expect(spec.layout["line-join"]).toBe("round");
  });

  it("omits line-cap / line-join when set to MapLibre defaults (butt/miter)", () => {
    const spec = transformToMapboxLayerStyleSpec(
      makeLineLayer({ stroke_cap: "butt", stroke_join: "miter" })
    ) as { layout: Record<string, unknown> };
    expect(spec.layout["line-cap"]).toBeUndefined();
    expect(spec.layout["line-join"]).toBeUndefined();
  });
});

describe("transformToLineDecorationLayers", () => {
  it("returns empty array when decoration_type is 'none'", () => {
    expect(transformToLineDecorationLayers(makeLineLayer())).toEqual([]);
    expect(
      transformToLineDecorationLayers(
        makeLineLayer({ decoration_type: "none", decoration_direction: "forward" })
      )
    ).toEqual([]);
  });

  it("returns one forward symbol layer for arrow + forward", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "forward",
        decoration_spacing: 250,
        // 32px target arrow on a 128px source raster → icon-size = 0.25.
        decoration_size: 32,
      })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].id).toBe("test-line-deco-fwd");
    expect(layers[0].type).toBe("symbol");
    expect(layers[0].layout["symbol-placement"]).toBe("line");
    expect(layers[0].layout["icon-image"]).toBe("arrow-sdf");
    expect(layers[0].layout["icon-rotate"]).toBe(0);
    expect(layers[0].layout["icon-rotation-alignment"]).toBe("map");
    expect(layers[0].layout["icon-size"]).toBe(0.25);
    expect(layers[0].layout["symbol-spacing"]).toBe(250);
  });

  it("returns one backward symbol layer with icon-rotate 180", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({ decoration_type: "arrow", decoration_direction: "backward" })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].id).toBe("test-line-deco-bwd");
    expect(layers[0].layout["icon-rotate"]).toBe(180);
  });

  it("returns two layers for arrow + both", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({ decoration_type: "arrow", decoration_direction: "both" })
    );
    expect(layers).toHaveLength(2);
    const fwd = layers.find((l) => l.id === "test-line-deco-fwd");
    const bwd = layers.find((l) => l.id === "test-line-deco-bwd");
    expect(fwd?.layout["icon-rotate"]).toBe(0);
    expect(bwd?.layout["icon-rotate"]).toBe(180);
  });

  it("propagates the line layer's stroke color expression to icon-color", () => {
    const sample = makeLineLayer({
      decoration_type: "arrow",
      decoration_direction: "forward",
      stroke_color: [255, 0, 0],
    });
    const layers = transformToLineDecorationLayers(sample);
    expect(layers[0].paint["icon-color"]).toEqual(getMapboxStyleColor(sample, "stroke_color"));
  });

  it("hides decorations when layer visibility is false", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        visibility: false,
        decoration_type: "arrow",
        decoration_direction: "forward",
      })
    );
    expect(layers[0].layout.visibility).toBe("none");
  });

  it("repeat placement uses sourceLayer 'default'", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "forward",
        decoration_placement: "repeat",
      })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].sourceLayer).toBe("default");
  });
});

describe("transformToLineDecorationLayers — backend-computed placements", () => {
  it("emits a point-symbol layer with default_decoration source-layer for placement=start, direction=forward", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "forward",
        decoration_placement: "start",
      })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].sourceLayer).toBe("default_decoration");
    expect(layers[0].layout["symbol-placement"]).toBe("point");
    expect(layers[0].layout["icon-rotate"]).toEqual(["-", ["get", "bearing"], 90]);
    expect(layers[0].id).toBe("test-line-deco-fwd-pt");
  });

  it("emits backward icon-rotate as bearing + 90 for placement=end", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "backward",
        decoration_placement: "end",
      })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].layout["icon-rotate"]).toEqual(["+", ["get", "bearing"], 90]);
    expect(layers[0].id).toBe("test-line-deco-bwd-pt");
  });

  it("emits two layers for direction=both with placement=start_and_end", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "both",
        decoration_placement: "start_and_end",
      })
    );
    expect(layers).toHaveLength(2);
    expect(layers.every((l) => l.sourceLayer === "default_decoration")).toBe(true);
    expect(layers.every((l) => l.layout["symbol-placement"] === "point")).toBe(true);
    expect(layers.map((l) => l.id).sort()).toEqual([
      "test-line-deco-bwd-pt",
      "test-line-deco-fwd-pt",
    ]);
  });

  it("repeat placement still uses source-layer 'default' and symbol-placement 'line'", () => {
    const layers = transformToLineDecorationLayers(
      makeLineLayer({
        decoration_type: "arrow",
        decoration_direction: "forward",
        decoration_placement: "repeat",
      })
    );
    expect(layers).toHaveLength(1);
    expect(layers[0].sourceLayer).toBe("default");
    expect(layers[0].layout["symbol-placement"]).toBe("line");
    expect(layers[0].id).toBe("test-line-deco-fwd");
  });
});
