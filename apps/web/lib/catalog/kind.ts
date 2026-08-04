import type { CatalogItem } from "@/lib/validations/catalog";

/**
 * What kind of thing a catalog result is.
 *
 * This lives on its own because reading it correctly needs care that must not be
 * duplicated: two of the properties involved are denormalised from the dataset
 * onto every one of its layers, so the same item answers differently depending on
 * where it is being shown. The card, its thumbnail and the detail view all have
 * to reach the same answer or one dataset appears to be several things.
 */

/**
 * `vector` covers point, line and polygon alike; `unknown` is for an item whose
 * kind genuinely cannot be told from what the catalog publishes.
 */
export type CatalogKind = "bundle" | "raster" | "table" | "vector" | "unknown";

/**
 * Pass `asMember` when the item is one layer of a bundle that is already on
 * screen. Both denormalised properties need it:
 *
 * - `goat:member_count` counts the layers of the **dataset**, and the mirror
 *   copies it onto every member — so a member claims to be a bundle of four
 *   unless the caller says otherwise.
 * - `goat:layerType` is likewise inherited from the collection, so a member of a
 *   bundle reports `bundle` as its own type.
 *
 * When the type is that inherited `bundle`, the item's own fields still settle
 * it: a geometry type means vector, and a row count without geometry means
 * tabular. Neither present is reported as `unknown` rather than guessed —
 * publishing item-level layer types (design open item 3) retires all of this.
 */
export const catalogKindOf = (item: CatalogItem, asMember?: boolean): CatalogKind => {
  const props = item.properties;
  if (!asMember && (props["goat:member_count"] ?? 1) > 1) return "bundle";
  switch (props["goat:layerType"]) {
    case "raster":
      return "raster";
    case "table":
      return "table";
    case "feature":
      return "vector";
    default:
      if (props["goat:geometryType"]) return "vector";
      if (typeof props["table:row_count"] === "number") return "table";
      return "unknown";
  }
};
