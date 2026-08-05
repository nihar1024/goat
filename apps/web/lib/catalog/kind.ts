import type { CatalogItem } from "@/lib/validations/catalog";

/** What kind of thing a catalog result is. */

/**
 * `vector` covers point, line and polygon alike; `unknown` is for an item whose
 * kind genuinely cannot be told from what the catalog publishes.
 */
export type CatalogKind = "bundle" | "raster" | "table" | "vector" | "unknown";

/** Pass `asMember` when the item is one layer of a bundle that is already on screen. */
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
