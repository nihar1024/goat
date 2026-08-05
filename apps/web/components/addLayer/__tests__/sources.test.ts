import { describe, expect, it } from "vitest";

import { ADD_LAYER_SOURCES, sourcesFor } from "@/components/addLayer/sources";

/**
 * The registry decides which tabs a host offers. Worth pinning because getting it
 * wrong is invisible in one host and broken in another: the datasets page has no
 * project, so a source that adds to one must not appear there.
 */
describe("sourcesFor", () => {
  it("offers every source inside a project", () => {
    expect(sourcesFor({ hasProject: true }).map((s) => s.id)).toEqual([
      "upload",
      "explorer",
      "catalog",
      "connections",
      "create",
    ]);
  });

  it("drops project-only sources without one", () => {
    const ids = sourcesFor({ hasProject: false }).map((s) => s.id);
    expect(ids).toEqual(["upload", "connections"]);
    // The three left out are exactly those that add a layer to a project.
    expect(ADD_LAYER_SOURCES.filter((s) => s.needsProject).map((s) => s.id)).toEqual([
      "explorer",
      "catalog",
      "create",
    ]);
  });

  it("gives every source either a flow or a handoff, never neither", () => {
    // A source with no flow and no handoff would render an empty tab.
    const withFlow = new Set(["upload", "create", "catalog"]);
    for (const source of ADD_LAYER_SOURCES) {
      expect(withFlow.has(source.id) || source.handoff !== undefined).toBe(true);
    }
  });

  it("keeps a label key for every source", () => {
    for (const source of ADD_LAYER_SOURCES) {
      expect(source.labelKey).toMatch(/^[a-z_]+$/);
    }
  });
});
