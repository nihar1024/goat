/**
 * @p4b/draw - Snap-to-layer support
 *
 * Provides a small singleton config that the host app can update, and a
 * helper for finding the closest snap target near the cursor by querying
 * rendered features on the map. Modes call these helpers in their pointer
 * handlers to adjust the click/move position before forwarding it.
 */

export type SnapTargetSource = "point" | "vertex";

export interface SnapTarget {
  lng: number;
  lat: number;
  source: SnapTargetSource;
}

export interface SnapConfig {
  /** Master enable flag. When false, snap helpers are no-ops. */
  enabled: boolean;
  /** Style layer ids to query for snap targets. */
  layerIds: string[];
  /** Pixel radius around the cursor used as the search bbox. */
  toleranceInPx: number;
}

let _config: SnapConfig = {
  enabled: false,
  layerIds: [],
  toleranceInPx: 12,
};

export function setSnapConfig(patch: Partial<SnapConfig>): void {
  _config = { ..._config, ...patch };
}

export function getSnapConfig(): SnapConfig {
  return _config;
}

interface MapLikePoint {
  x: number;
  y: number;
}

interface MapLikeLngLat {
  lng: number;
  lat: number;
}

export interface SnapMapLike {
  queryRenderedFeatures: (
    geometry: [[number, number], [number, number]],
    options?: { layers?: string[] }
  ) => Array<{ geometry?: GeoJSON.Geometry }>;
  project: (lngLat: [number, number]) => MapLikePoint;
  /** Optional — used to filter the configured layer ids to those that
   *  actually exist on the current style. Without it, querying a missing
   *  layer would throw. */
  getLayer?: (id: string) => unknown;
}

function pushCoords(out: [number, number][], coords: GeoJSON.Position[]): void {
  for (const c of coords) out.push(c as [number, number]);
}

function collectCandidateCoords(g: GeoJSON.Geometry, out: [number, number][] = []): [number, number][] {
  switch (g.type) {
    case "Point":
      out.push(g.coordinates as [number, number]);
      break;
    case "MultiPoint":
      pushCoords(out, g.coordinates);
      break;
    case "LineString":
      pushCoords(out, g.coordinates);
      break;
    case "MultiLineString":
      for (const line of g.coordinates) pushCoords(out, line);
      break;
    case "Polygon":
      for (const ring of g.coordinates) pushCoords(out, ring);
      break;
    case "MultiPolygon":
      for (const poly of g.coordinates) {
        for (const ring of poly) pushCoords(out, ring);
      }
      break;
    case "GeometryCollection":
      for (const inner of g.geometries) collectCandidateCoords(inner, out);
      break;
  }
  return out;
}

export function findSnapTarget(
  map: SnapMapLike,
  cursorPx: MapLikePoint
): SnapTarget | null {
  const cfg = _config;
  if (!cfg.enabled || cfg.layerIds.length === 0) return null;

  // Filter to layer ids that actually exist on the current style — querying
  // a missing layer throws. Done every call so layer add/remove never leaves
  // stale state.
  let activeLayerIds = cfg.layerIds;
  if (typeof map.getLayer === "function") {
    activeLayerIds = cfg.layerIds.filter((id) => {
      try {
        return Boolean(map.getLayer!(id));
      } catch {
        return false;
      }
    });
  }
  if (activeLayerIds.length === 0) return null;

  const tol = cfg.toleranceInPx;
  const bbox: [[number, number], [number, number]] = [
    [cursorPx.x - tol, cursorPx.y - tol],
    [cursorPx.x + tol, cursorPx.y + tol],
  ];

  let features: Array<{ geometry?: GeoJSON.Geometry }> = [];
  try {
    features = map.queryRenderedFeatures(bbox, { layers: activeLayerIds });
  } catch {
    return null;
  }

  if (features.length === 0) return null;

  const tolSq = tol * tol;
  let bestDistanceSq = tolSq + 1;
  let best: SnapTarget | null = null;

  for (const f of features) {
    const g = f.geometry;
    if (!g) continue;

    // Points beat vertices when distances are equal — but we only compute
    // distance once per candidate, so we just bias by source kind on ties.
    const isPointGeom = g.type === "Point" || g.type === "MultiPoint";
    const candidates = collectCandidateCoords(g, []);

    for (const c of candidates) {
      let px: MapLikePoint;
      try {
        px = map.project([c[0], c[1]]);
      } catch {
        continue;
      }
      const dx = px.x - cursorPx.x;
      const dy = px.y - cursorPx.y;
      const d2 = dx * dx + dy * dy;
      if (d2 > tolSq) continue;
      if (d2 < bestDistanceSq || (d2 === bestDistanceSq && isPointGeom && best?.source === "vertex")) {
        bestDistanceSq = d2;
        best = {
          lng: c[0],
          lat: c[1],
          source: isPointGeom ? "point" : "vertex",
        };
      }
    }
  }

  return best;
}

export interface DrawEventLike {
  point: MapLikePoint;
  lngLat: MapLikeLngLat;
}

/**
 * If the map cursor is within snap tolerance of a layer feature, returns the
 * snap target and a shallow-cloned event whose lngLat is at the snapped
 * position. Otherwise returns the original event and a null target.
 *
 * Intentionally non-mutating — modes pass the returned event to their parent.
 */
export function applySnapToEvent<T extends DrawEventLike>(
  map: SnapMapLike | undefined,
  e: T
): { event: T; snap: SnapTarget | null } {
  if (!map || !e?.point || !e.lngLat) return { event: e, snap: null };
  const target = findSnapTarget(map, e.point);
  if (!target) return { event: e, snap: null };
  return {
    event: { ...e, lngLat: { lng: target.lng, lat: target.lat } } as T,
    snap: target,
  };
}
