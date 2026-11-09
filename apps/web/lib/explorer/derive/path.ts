/**
 * A path: the stretch of a pattern between two of its stops in a row (board
 * 21, "Path between two stops"), the level below a direction where reroutes,
 * inserted stops and running times between stops apply.
 *
 * A click on the pattern's line picks it: the click is placed along the
 * pattern's shape (the nearest point of the line, as the shape's metres
 * `shape_points.d` run), and the path is the one between the last stop at or
 * before that point and the next. Stops are placed along the shape by the
 * snapshot (`pattern_shape_stops`).
 */
import type { SqlRunner } from "@/lib/explorer/db/types";
import { cut } from "@/lib/explorer/derive/patternSections";

export interface PatternPath {
  pattern_idx: number;
  /** The two stops, by their place in the pattern (0-based) and name. */
  from_i: number;
  to_i: number;
  from_name: string;
  to_name: string;
  /** The two stops' stop_idx, and the line the pattern is of: what an edit
   * on the path (a reroute) starts from. */
  from_stop: number;
  to_stop: number;
  route_idx: number;
  /** The line between them, along the shape. */
  line: [number, number][];
}

/** Metres per degree of latitude: the local plane the click is placed on. */
const M_PER_DEG = 111_195;

/** The path of `pattern_idx` nearest to `[lon, lat]`, or null when the
 * pattern has no line (a pattern of one stop). */
export async function pathAt(
  db: SqlRunner,
  pattern_idx: number,
  lon: number,
  lat: number
): Promise<PatternPath | null> {
  const stops = await db.all<{
    shape_idx: number;
    i: number;
    d: number;
    name: string;
    stop_idx: number;
    route_idx: number;
  }>(`
    SELECT pss.shape_idx, pss.i, pss.d, s.name, s.stop_idx, p.route_idx
    FROM pattern_shape_stops pss
    JOIN patterns p USING (pattern_idx)
    JOIN stops s ON s.stop_idx = p.stops[pss.i + 1]
    WHERE pss.pattern_idx = ${pattern_idx} AND pss.d IS NOT NULL
      AND pss.shape_idx = (SELECT min(shape_idx) FROM pattern_shape_stops
                           WHERE pattern_idx = ${pattern_idx} AND d IS NOT NULL)
    ORDER BY pss.i`);
  if (stops.length < 2) return null;
  const shape_idx = stops[0].shape_idx;
  const points = await db.all<{ lon: number; lat: number; d: number }>(
    `SELECT lon, lat, d FROM shape_points WHERE shape_idx = ${shape_idx} ORDER BY i`
  );
  if (points.length < 2) return null;

  // The click's distance along the shape: its nearest point on the line.
  const kx = Math.cos((lat * Math.PI) / 180) * M_PER_DEG;
  let best = Infinity;
  let along = points[0].d;
  for (let k = 1; k < points.length; k++) {
    const a = points[k - 1];
    const b = points[k];
    const [ax, ay] = [(a.lon - lon) * kx, (a.lat - lat) * M_PER_DEG];
    const [bx, by] = [(b.lon - lon) * kx, (b.lat - lat) * M_PER_DEG];
    const [dx, dy] = [bx - ax, by - ay];
    const len2 = dx * dx + dy * dy;
    const f = len2 ? Math.min(1, Math.max(0, -(ax * dx + ay * dy) / len2)) : 0;
    const [px, py] = [ax + dx * f, ay + dy * f];
    const dist = px * px + py * py;
    if (dist < best) {
      best = dist;
      along = a.d + (b.d - a.d) * f;
    }
  }

  // The stops either side of it; past the last stop, the last stretch.
  let k = 0;
  while (k < stops.length - 2 && stops[k + 1].d <= along) k++;
  const [from, to] = [stops[k], stops[k + 1]];
  return {
    pattern_idx,
    from_i: from.i,
    to_i: to.i,
    from_name: from.name,
    to_name: to.name,
    from_stop: from.stop_idx,
    to_stop: to.stop_idx,
    route_idx: from.route_idx,
    line: cut(points, from.d, to.d),
  };
}

/** The pattern a trip runs. */
export async function tripPattern(db: SqlRunner, trip_idx: number): Promise<number | null> {
  const [row] = await db.all<{ pattern_idx: number | null }>(
    `SELECT pattern_idx FROM trips WHERE trip_idx = ${trip_idx}`
  );
  return row?.pattern_idx ?? null;
}
