/**
 * Edit line attributes (01-editing-operations § 1): a line's own GTFS
 * fields (routes.txt), from its Properties tab, as a stop's are from its
 * (2.4). Checked by GTFS's rules, each on its field, so Apply waits without
 * a word: a name, short or long; colours as six hex digits; a full URL; a
 * sort order that is a whole number. Its ID stays: trips and other tables
 * name it.
 */
import type { SqlRunner } from "@/lib/explorer/db/types";
import type { Built } from "@/lib/explorer/edit/ops/types";
import { sqlNumber, sqlText } from "@/lib/explorer/edit/sql";
import type { GtfsValue } from "@/lib/explorer/edit/types";

/** GTFS continuous_pickup / continuous_drop_off: 0 continuous, 2 phone the
 * agency, 3 coordinate with the driver; none (empty, or 1) not continuous. */
export type Continuous = 0 | 2 | 3 | null;

/** A line's own fields, as Properties edits them; text as typed. */
export interface RouteValues {
  short_name: string;
  long_name: string;
  description: string;
  route_type: number;
  agency_idx: number;
  color: string;
  text_color: string;
  url: string;
  sort_order: string;
  continuous_pickup: Continuous;
  continuous_drop_off: Continuous;
}
export type RouteField = keyof RouteValues;
export const ROUTE_VALUE_KEYS: RouteField[] = [
  "short_name",
  "long_name",
  "description",
  "route_type",
  "agency_idx",
  "color",
  "text_color",
  "url",
  "sort_order",
  "continuous_pickup",
  "continuous_drop_off",
];

export interface RouteRecord extends RouteValues {
  route_idx: number;
  route_id: string;
}

/** Each value's snapshot column and GTFS field. */
const COLUMNS: Record<RouteField, { snapshot: string; gtfs: string }> = {
  short_name: { snapshot: "short_name", gtfs: "route_short_name" },
  long_name: { snapshot: "long_name", gtfs: "route_long_name" },
  description: { snapshot: "description", gtfs: "route_desc" },
  route_type: { snapshot: "route_type", gtfs: "route_type" },
  agency_idx: { snapshot: "agency_idx", gtfs: "agency_id" },
  color: { snapshot: "color", gtfs: "route_color" },
  text_color: { snapshot: "text_color", gtfs: "route_text_color" },
  url: { snapshot: "url", gtfs: "route_url" },
  sort_order: { snapshot: "sort_order", gtfs: "route_sort_order" },
  continuous_pickup: { snapshot: "continuous_pickup", gtfs: "continuous_pickup" },
  continuous_drop_off: { snapshot: "continuous_drop_off", gtfs: "continuous_drop_off" },
};

const continuous = (v: unknown): Continuous => (v === 0 || v === 2 || v === 3 ? v : null);

export async function routeRecord(db: SqlRunner, route_idx: number): Promise<RouteRecord | null> {
  const [row] = await db.all<Record<string, string | number | null>>(`
    SELECT route_idx, route_id, short_name, long_name, description, route_type, agency_idx, color,
           text_color, url, sort_order, continuous_pickup, continuous_drop_off
    FROM routes WHERE route_idx = ${sqlNumber(route_idx)}`);
  if (!row) return null;
  const text = (k: string) => (row[k] === null ? "" : String(row[k]));
  return {
    route_idx: Number(row.route_idx),
    route_id: String(row.route_id),
    short_name: text("short_name"),
    long_name: text("long_name"),
    description: text("description"),
    route_type: Number(row.route_type ?? 3),
    agency_idx: Number(row.agency_idx ?? 0),
    color: text("color"),
    text_color: text("text_color"),
    url: text("url"),
    sort_order: text("sort_order"),
    continuous_pickup: continuous(row.continuous_pickup === null ? null : Number(row.continuous_pickup)),
    continuous_drop_off: continuous(
      row.continuous_drop_off === null ? null : Number(row.continuous_drop_off)
    ),
  };
}

/** The values as saved: text trimmed, colours upper case without a `#`. */
export function cleanRouteValues(v: RouteValues): RouteValues {
  const hex = (x: string) => x.trim().replace(/^#/, "").toUpperCase();
  return {
    ...v,
    short_name: v.short_name.trim(),
    long_name: v.long_name.trim(),
    description: v.description.trim(),
    color: hex(v.color),
    text_color: hex(v.text_color),
    url: v.url.trim(),
    sort_order: v.sort_order.trim(),
  };
}

export function sameRouteValues(a: RouteValues, b: RouteValues): boolean {
  const x = cleanRouteValues(a);
  const y = cleanRouteValues(b);
  return ROUTE_VALUE_KEYS.every((k) => x[k] === y[k]);
}

const HEX_RE = /^[0-9A-F]{6}$/;

/** Each field's problem, by GTFS's rules, as an explorer_field_* code. */
export function routeFieldProblems(values: RouteValues): Partial<Record<RouteField, string>> {
  const v = cleanRouteValues(values);
  const problems: Partial<Record<RouteField, string>> = {};
  if (!v.short_name && !v.long_name) {
    problems.short_name = "route_both_short_and_long_name_missing";
    problems.long_name = "route_both_short_and_long_name_missing";
  }
  if (v.color && !HEX_RE.test(v.color)) problems.color = "invalid_color";
  if (v.text_color && !HEX_RE.test(v.text_color)) problems.text_color = "invalid_color";
  if (v.url) {
    try {
      const u = new URL(v.url);
      if (u.protocol !== "http:" && u.protocol !== "https:") problems.url = "invalid_url";
    } catch {
      problems.url = "invalid_url";
    }
  }
  if (v.sort_order && !/^\d+$/.test(v.sort_order)) problems.sort_order = "invalid_sort_order";
  return problems;
}

export interface RouteDetailsFacts {
  route_id: string;
  /** The line as riders know it, before. */
  line: string;
  from: RouteValues;
  to: RouteValues;
  changed: RouteField[];
}

/** The line's fields, as the draft has them. */
export async function editRouteDetails(
  db: SqlRunner,
  route_idx: number,
  values: RouteValues
): Promise<Built<RouteDetailsFacts>> {
  const route = await routeRecord(db, route_idx);
  if (!route) throw new Error(`No route ${route_idx}`);
  const to = cleanRouteValues(values);
  const from = cleanRouteValues(route);
  const changed = ROUTE_VALUE_KEYS.filter((k) => from[k] !== to[k]);
  const facts: RouteDetailsFacts = {
    route_id: route.route_id,
    line: from.short_name || from.long_name || route.route_id,
    from,
    to,
    changed,
  };
  // Only problems of the fields it changes: the feed's own are the feed's.
  const problems = routeFieldProblems(to);
  const field = changed.find((k) => problems[k]);
  if (field)
    return {
      ok: false,
      refused: { code: problems[field] as string, severity: "error", field },
      facts,
      checks: [],
    };

  const set: string[] = [];
  const gtfs: Record<string, GtfsValue> = {};
  for (const k of changed) {
    const { snapshot, saved } = await stored(db, k, to);
    set.push(`${COLUMNS[k].snapshot} = ${snapshot}`);
    gtfs[COLUMNS[k].gtfs] = saved;
  }
  const where = `route_idx = ${sqlNumber(route_idx)}`;
  return {
    ok: true,
    facts,
    checks: [],
    rows: {
      kind: "route_details",
      touches: [{ table: "routes", where }],
      sql: set.length ? [`UPDATE routes SET ${set.join(", ")} WHERE ${where}`] : [],
      gtfs: set.length
        ? [{ role: "routes", op: "update", key: { route_id: route.route_id }, values: gtfs }]
        : [],
    },
  };
}

/** A value as the snapshot and the bundle keep it: empty text none. */
async function stored(
  db: SqlRunner,
  k: RouteField,
  v: RouteValues
): Promise<{ snapshot: string; saved: GtfsValue }> {
  if (k === "agency_idx") {
    const [a] = await db.all<{ agency_id: string | null }>(
      `SELECT agency_id FROM agencies WHERE agency_idx = ${sqlNumber(v.agency_idx)}`
    );
    return { snapshot: sqlNumber(v.agency_idx), saved: a?.agency_id || null };
  }
  if (k === "route_type" || k === "continuous_pickup" || k === "continuous_drop_off") {
    const n = v[k];
    return { snapshot: sqlNumber(n), saved: n };
  }
  if (k === "sort_order") {
    const n = v.sort_order ? Number(v.sort_order) : null;
    return { snapshot: sqlNumber(n), saved: n };
  }
  const text = (v[k] as string) || null;
  return { snapshot: sqlText(text), saved: text };
}
