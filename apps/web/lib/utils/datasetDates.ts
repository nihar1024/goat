import type { Layer } from "@/lib/validations/layer";
import type { ProjectLayer } from "@/lib/validations/project";

/**
 * When the dataset behind a layer was last updated.
 *
 * For an ordinary layer that is `updated_at` — GOAT holds the data, so the row
 * and the data change together. A catalog layer is a copy of someone else's
 * dataset: its `updated_at` records when GOAT promoted or re-materialized that
 * copy, which for a freshly added layer is "a few seconds ago" no matter how
 * old the data is. The catalog record carries the provider's own `updated`, and
 * that is what a reader means by "last updated".
 *
 * Snapshots taken before that field was promoted do not carry it, so the layer's
 * own timestamp remains the fallback rather than showing nothing.
 */
export function datasetUpdatedAt(dataset: Layer | ProjectLayer): string | undefined {
  const catalogItem = (
    dataset.other_properties as { catalog_item?: { updated?: string | null } } | undefined
  )?.catalog_item;
  return catalogItem?.updated ?? dataset.updated_at ?? undefined;
}
