/**
 * Edits being made: drafts, outside the snapshot until Apply (spec 01,
 * "Drafts sit outside the bundle"). One at a time, in Redux, so the panel
 * that fills it in and the Apply bar that applies it read the same thing;
 * Cancel, Esc or picking something else lets it go with no trace.
 */
import type { LineScope } from "@/lib/explorer/edit/ops/lineStops";

/** GTFS wheelchair_boarding: 0 unknown (or as its station), 1 accessible,
 * 2 not. */
export type Wheelchair = 0 | 1 | 2;

/** GTFS location_type: 0 stop or platform, 1 station, 2 entrance or exit,
 * 3 generic node, 4 boarding area. The Explorer makes the first three, each
 * keeping its type once made; a feed's nodes and boarding areas are shown,
 * not edited. */
export type LocationType = 0 | 1 | 2 | 3 | 4;
export const EDITABLE_LOCATION_TYPES = [0, 1, 2] as const;

/** A stop's own GTFS fields, as Properties edits them; text as typed, an
 * empty one none. */
export interface StopValues {
  name: string;
  wheelchair: Wheelchair;
  location_type: LocationType;
  /** The station (or, for a boarding area, platform) it belongs to. */
  parent_idx: number | null;
  platform_code: string;
}

export const NO_STOP_VALUES: StopValues = {
  name: "",
  wheelchair: 0,
  location_type: 0,
  parent_idx: null,
  platform_code: "",
};

export type EditDraft =
  /** 2.4: a stop's details, as the Details tab has them. */
  | { kind: "stop-details"; stop_idx: number; values: StopValues }
  /** 2.1: a stop placed with the Stop tool, where it was clicked. */
  /** Its id null until one is drawn for it. */
  | { kind: "stop-new"; lon: number; lat: number; stop_id: string | null; values: StopValues }
  /** 2.3: a stop deleted, with all that calls there. */
  | { kind: "stop-delete"; stop_idx: number }
  /** 2.2: a stop dragged to a new place, its paths with it. */
  | { kind: "stop-move"; stop_idx: number; lon: number; lat: number }
  /** 3.2: a stop taken off a line, for the trips its scope takes. */
  | { kind: "line-stop-remove"; stop_idx: number; scope: LineScope }
  /** 3.1: a stop added to a line between `a` and `b`, for the trips its
   * scope takes; picked on the map (null until then). */
  | { kind: "line-stop-add"; a: number; b: number; stop_idx: number | null; scope: LineScope }
  /** 1.2: the path from `a` to `b` (stops called back to back, drawn from
   * `ends`) dragged through `via`, for the trips its scope takes. */
  | {
      kind: "line-reroute";
      a: number;
      b: number;
      ends: [[number, number], [number, number]];
      via: [number, number][];
      scope: LineScope;
    };
