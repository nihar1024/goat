import { describe, expect, it } from "vitest";

import { findPopupLayer, shouldClosePopupForHiddenLayer } from "../popupVisibility";

// Minimal layer shapes matching how popupInfo.layerId is resolved:
// popupInfo.layerId is set to `layer_id ?? id` at dispatch time.
const projectLayer = (over: Partial<Record<string, unknown>> = {}) => ({
  id: 42,
  layer_id: "dataset-abc",
  properties: { visibility: true },
  ...over,
});

describe("findPopupLayer", () => {
  it("matches on layer_id (ProjectLayer)", () => {
    const layers = [projectLayer()];
    expect(findPopupLayer("dataset-abc", layers)).toBe(layers[0]);
  });

  it("matches on stringified id (plain Layer)", () => {
    const layers = [{ id: 7, properties: { visibility: true } }];
    expect(findPopupLayer("7", layers)).toBe(layers[0]);
  });

  it("returns undefined when no layer matches", () => {
    expect(findPopupLayer("missing", [projectLayer()])).toBeUndefined();
  });

  it("returns undefined for a missing layerId or layers list", () => {
    expect(findPopupLayer(undefined, [projectLayer()])).toBeUndefined();
    expect(findPopupLayer("dataset-abc", undefined)).toBeUndefined();
  });
});

describe("shouldClosePopupForHiddenLayer", () => {
  it("closes when the owning layer's visibility is toggled off", () => {
    const layers = [projectLayer({ properties: { visibility: false } })];
    expect(shouldClosePopupForHiddenLayer("dataset-abc", layers)).toBe(true);
  });

  it("keeps the popup while the owning layer is visible", () => {
    expect(shouldClosePopupForHiddenLayer("dataset-abc", [projectLayer()])).toBe(false);
  });

  it("treats a missing visibility flag as visible (default true)", () => {
    const layers = [projectLayer({ properties: {} })];
    expect(shouldClosePopupForHiddenLayer("dataset-abc", layers)).toBe(false);
  });

  it("closes when the owning layer was removed from the project", () => {
    expect(shouldClosePopupForHiddenLayer("dataset-abc", [])).toBe(true);
  });

  it("does not close while layers are still unknown (undefined during load/refetch)", () => {
    expect(shouldClosePopupForHiddenLayer("dataset-abc", undefined)).toBe(false);
  });

  it("does not act when there is no owning layerId", () => {
    expect(shouldClosePopupForHiddenLayer(undefined, [projectLayer()])).toBe(false);
  });
});
