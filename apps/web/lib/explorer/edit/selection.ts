/**
 * What is selected, as one level (board 21): a line, one of its directions
 * or variants, and below it a path between two stops, a trip or a stop — one
 * at a time. Read from the state the views already share, not kept twice:
 * the selected line, the direction choice, the path, the right panel's item.
 *
 * The level sets what an edit applies to by default (the Apply bar's scope):
 * the whole line, the direction or the variant, the pattern a path is of,
 * the trip, or a stop on every line that calls at it.
 */
import { type ExplorerState, panelItem } from "@/lib/store/explorer/slice";

export type SelectionLevel = "route" | "direction" | "path" | "trip" | "stop";
export type ApplyScope = "route" | "direction" | "pattern" | "trip" | "stop";

export function selectionLevel(state: ExplorerState): SelectionLevel | null {
  if (state.path) return "path";
  const item = panelItem(state);
  if (item?.kind === "trip") return "trip";
  if (item?.kind === "stop") return "stop";
  if (state.selectedRouteId && state.pattern) return "direction";
  if (state.selectedRouteId) return "route";
  return null;
}

/** The default "Apply to" for what is selected. */
export function selectionScope(state: ExplorerState): ApplyScope | null {
  switch (selectionLevel(state)) {
    case "route":
      return "route";
    case "direction":
      return state.pattern?.pattern_idx != null ? "pattern" : "direction";
    case "path":
      return "pattern";
    case "trip":
      return "trip";
    case "stop":
      return "stop";
    default:
      return null;
  }
}
