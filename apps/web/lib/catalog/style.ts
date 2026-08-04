import { transformToMapboxLayerStyleSpec } from "@/lib/transformers/layer";
import type { Layer } from "@/lib/validations/layer";

/**
 * A catalog dataset's own rendering, as MapLibre paint.
 *
 * The harvester publishes a style object per layer — 10,685 of the catalog's
 * 10,793 have one — in exactly the shape a GOAT layer carries in `properties`:
 *
 *     {"color": [102,194,165], "filled": true, "opacity": 0.8, "stroked": false,
 *      "color_field": {"name": "measure", "type": "number"},
 *      "color_range": {"name": "YlGnBu", "type": "sequential", "colors": [...]}}
 *
 * which is why this reuses the app's own transformer rather than reimplementing
 * it: a preview drawn by different code than the map would diverge from it, and
 * data-driven styling (`color_field` + `color_range`, a real choropleth) is
 * exactly the part nobody wants to write twice. The same style is what promote
 * applies when a dataset becomes a layer, so the preview shows what the dataset
 * will look like once added — which is the whole point of a preview.
 */

/** The published style object: a layer's `properties`, before it is a layer. */
export type CatalogStyle = Layer["properties"];

export type CatalogPaint = {
  type: string;
  layout?: Record<string, unknown>;
  paint: Record<string, unknown>;
};

/**
 * `undefined` when the style cannot be drawn, which the caller renders as its
 * plain footprint colour instead.
 *
 * Three ways that happens, all of them expected rather than exceptional: the
 * dataset states no geometry type (108 of 10,793 layers), it states one this
 * renderer has no shape for (a raster), or the style itself is malformed. The
 * last is why this catches: the object is published upstream, so a field of the
 * wrong type must degrade to "no style" and never take the map down with it.
 */
export const catalogPaint = (
  style: CatalogStyle | undefined,
  geometryType: string | undefined
): CatalogPaint | undefined => {
  if (!style || !geometryType) return undefined;
  if (geometryType !== "point" && geometryType !== "line" && geometryType !== "polygon") {
    return undefined;
  }
  try {
    // The transformer reads exactly two members off its argument —
    // `properties` and `feature_layer_geometry_type` — so a catalog style needs
    // no layer, only those two. Cast rather than build a whole Layer: inventing
    // ids and dates would put fiction in front of code that might later read them.
    return transformToMapboxLayerStyleSpec({
      properties: style,
      feature_layer_geometry_type: geometryType,
    } as unknown as Layer) as CatalogPaint;
  } catch {
    return undefined;
  }
};
