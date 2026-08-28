import { describe, expect, it } from "vitest";

import { datasetUpdatedAt } from "@/lib/utils/datasetDates";

const PROMOTED_AT = "2026-08-28T18:50:55.507Z";
const SOURCE_UPDATED = "2026-08-16T10:55:42.000Z";

const layer = (other_properties?: unknown) =>
  ({ updated_at: PROMOTED_AT, other_properties }) as never;

describe("datasetUpdatedAt", () => {
  it("uses the layer's own timestamp for an ordinary layer", () => {
    expect(datasetUpdatedAt(layer())).toBe(PROMOTED_AT);
  });

  it("prefers the catalog record's date for a catalog layer", () => {
    // `updated_at` on a promoted layer is when GOAT copied the dataset, so a
    // layer added today reported "2 minutes ago" for data published in August.
    expect(datasetUpdatedAt(layer({ catalog_item: { updated: SOURCE_UPDATED } }))).toBe(
      SOURCE_UPDATED
    );
  });

  it("falls back to the layer for a snapshot taken before the date was promoted", () => {
    expect(datasetUpdatedAt(layer({ catalog_item: { title: "Gebührenzonen" } }))).toBe(
      PROMOTED_AT
    );
  });

  it("returns nothing when neither is known", () => {
    expect(datasetUpdatedAt({ other_properties: {} } as never)).toBeUndefined();
  });
});
