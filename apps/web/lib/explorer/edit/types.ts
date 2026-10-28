/**
 * The Explorer's edits: what a change is, in the browser and on the server.
 *
 * A change applies twice, in two forms. In the browser it changes the
 * snapshot's tables (indexed: `trip_idx`, `stop_idx`), so every panel shows
 * it at once. On save it is sent as rows of the bundle's GTFS tables, keyed by
 * GTFS ids — the snapshot's indexes mean nothing outside one build — and
 * geoapi writes those (`POST /bundles/{id}/changes`, goatlib's
 * `bundles/explorer/changeset.py`).
 */

/** The bundle tables a change may write (goatlib `ROLE_KEYS`). */
export type GtfsRole =
  | "agency"
  | "stops"
  | "routes"
  | "trips"
  | "stop_times"
  | "calendar"
  | "calendar_dates"
  | "frequencies"
  | "shapes";

/** A value as GTFS writes it: a time `25:10:00`, a date `20261012`. */
export type GtfsValue = string | number | null;

/** One row of a bundle table written: inserted whole, updated in the columns
 * given, or deleted; `key` is its GTFS primary key. */
export interface GtfsRowOp {
  role: GtfsRole;
  op: "insert" | "update" | "delete";
  key: Record<string, GtfsValue>;
  values?: Record<string, GtfsValue>;
}

/** Rows of one snapshot table a change may alter, by a condition that
 * selects them before and after it: undo puts back exactly these rows. */
export interface Touch {
  table: string;
  where: string;
}

/** What the user reads of a change: in the change list, the exit dialog. */
export interface ChangeSummary {
  id: string;
  /** Which edit (`stop_rename`, `headway`, …): the list's icon. */
  kind: string;
  label: string;
  /** "+5 trips a weekday · +3 peak vehicles". */
  impact?: string;
  /** The change in annual operating cost, ≈, in the settings' currency. */
  cost?: number;
}

/** One change, ready to apply. */
export interface EditChange extends ChangeSummary {
  /** The snapshot rows it alters, and the statements that alter them. */
  touches: Touch[];
  sql: string[];
  /** The same change as bundle rows, for the save. */
  gtfs: GtfsRowOp[];
}
