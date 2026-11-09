import { describe, expect, it } from "vitest";

import { selectionLevel, selectionScope } from "@/lib/explorer/edit/selection";
import {
  clearExplorerSelection,
  clickExplorerPath,
  explorerReducer,
  openExplorer,
  openExplorerPanel,
  pickExplorerPattern,
  selectExplorerRoute,
  setExplorerPath,
} from "@/lib/store/explorer/slice";

const open = () =>
  explorerReducer(
    explorerReducer(undefined, { type: "init" }),
    openExplorer({ bundleId: "b1", bundleName: "Feed" })
  );
const PATH = {
  pattern_idx: 4,
  from_i: 1,
  to_i: 2,
  from_name: "Second",
  to_name: "Third",
  from_stop: 1,
  to_stop: 2,
  route_idx: 0,
};
const STOP = { stop_idx: 4, name: "Fourth", lon: 13.43, lat: 52.5 };

describe("the selection", () => {
  it("goes down a level at a time, each with its scope", () => {
    let state = open();
    expect(selectionLevel(state)).toBeNull();
    state = explorerReducer(state, selectExplorerRoute("R1"));
    expect([selectionLevel(state), selectionScope(state)]).toEqual(["route", "route"]);
    state = explorerReducer(state, pickExplorerPattern({ direction: 3, pattern_idx: null }));
    expect([selectionLevel(state), selectionScope(state)]).toEqual(["direction", "direction"]);
    state = explorerReducer(state, pickExplorerPattern({ direction: 3, pattern_idx: 5 }));
    expect(selectionScope(state)).toBe("pattern");
    state = explorerReducer(state, setExplorerPath(PATH));
    expect([selectionLevel(state), selectionScope(state)]).toEqual(["path", "pattern"]);
  });

  it("holds one of a path, a trip and a stop", () => {
    let state = explorerReducer(open(), selectExplorerRoute("R1"));
    state = explorerReducer(state, openExplorerPanel({ item: { kind: "stop", stop: STOP } }));
    expect([selectionLevel(state), selectionScope(state)]).toEqual(["stop", "stop"]);
    state = explorerReducer(state, setExplorerPath(PATH));
    expect(selectionLevel(state)).toBe("path");
    expect(state.panel.stack).toEqual([]);
    state = explorerReducer(state, openExplorerPanel({ item: { kind: "trip", trip_idx: 2, run_dep_s: 0 } }));
    expect([selectionLevel(state), selectionScope(state)]).toEqual(["trip", "trip"]);
    expect(state.path).toBeNull();
  });

  it("lets a path go with its direction or line", () => {
    let state = explorerReducer(open(), selectExplorerRoute("R1"));
    state = explorerReducer(state, setExplorerPath(PATH));
    expect(explorerReducer(state, pickExplorerPattern({ direction: 7, pattern_idx: null })).path).toBeNull();
    expect(explorerReducer(state, selectExplorerRoute("R2")).path).toBeNull();
  });

  it("waits for a click on the line to be placed, then holds the path", () => {
    let state = explorerReducer(open(), clickExplorerPath({ lon: 13.4, lat: 52.5 }));
    state = explorerReducer(state, clickExplorerPath({ lon: 13.41, lat: 52.5 }));
    expect(state.pathClick).toEqual({ lon: 13.41, lat: 52.5, n: 2 });
    state = explorerReducer(state, setExplorerPath(PATH));
    expect(state.pathClick).toBeNull();
  });

  it("is cleared whole by Esc", () => {
    let state = explorerReducer(open(), selectExplorerRoute("R1"));
    state = explorerReducer(state, setExplorerPath(PATH));
    state = explorerReducer(state, clearExplorerSelection());
    expect(selectionLevel(state)).toBeNull();
    expect(state.selectedRouteId).toBeNull();
  });
});
