/**
 * The edits on a stop of the selected line (01-editing-operations § 3),
 * started from wherever they are offered — the Stops tab, a right click on
 * the map — alike: the same draft, the same scope to start from (the
 * variant picked, else the direction; a trip of the line open in the right
 * panel, the narrowest it may take). The Apply bar widens or narrows it.
 */
import { useCallback } from "react";

import { shownPattern } from "@/lib/explorer/directionChoice";
import type { LineScope } from "@/lib/explorer/edit/ops/lineStops";
import {
  type ExplorerPatternChoice,
  type ExplorerRouteDrawing,
  openExplorerPanel,
  panelItem,
  setEditDraft,
} from "@/lib/store/explorer/slice";

import { useRoutes } from "@/hooks/explorer/useExplorerData";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";

export interface LineStopRef {
  stop_idx: number;
  name: string;
  lat: number | null;
  lon: number | null;
}

/** Where an edit on line `route_idx`, drawn as `drawing`, starts: the
 * variant picked, else the direction shown; `trip_idx` the trip of it open. */
export function lineScope(
  route_idx: number,
  drawing: ExplorerRouteDrawing,
  choice: ExplorerPatternChoice | null,
  trip_idx: number | null
): LineScope | null {
  const direction = drawing.directions.find((d) => d.key === choice?.direction) ?? drawing.directions[0];
  const pattern_idx = shownPattern(choice, drawing.directions);
  if (!direction || pattern_idx === null) return null;
  const variant = choice?.pattern_idx != null && direction.patterns.includes(choice.pattern_idx);
  return {
    route_idx,
    level: variant ? "variant" : "direction",
    pattern_idx,
    direction: direction.patterns,
    trip_idx,
  };
}

export function useLineStopEdits() {
  const dispatch = useAppDispatch();
  const { db } = useExplorer();
  const routeId = useAppSelector((s) => s.explorer.selectedRouteId);
  const route = useRoutes(db).data?.find((r) => r.route_id === routeId);
  const drawing = useAppSelector((s) => s.explorer.drawing);
  const choice = useAppSelector((s) => s.explorer.pattern);
  const openTrip = useAppSelector((s) => {
    const item = panelItem(s.explorer);
    return item?.kind === "trip" ? item.trip_idx : null;
  });

  /** Where an edit on the line starts; null with no line selected. */
  const scope = useCallback((): LineScope | null => {
    if (!route || !drawing || drawing.routeId !== route.route_id) return null;
    const ofLine =
      openTrip !== null && route.trip_lo !== null && route.trip_hi !== null
        ? openTrip >= route.trip_lo && openTrip <= route.trip_hi
        : false;
    return lineScope(route.route_idx, drawing, choice, ofLine ? openTrip : null);
  }, [route, drawing, choice, openTrip]);

  /** 3.1: a stop to add between `a` and `b`, picked on the map next. */
  const insertBetween = useCallback(
    (a: number, b: number) => {
      const s = scope();
      if (s) dispatch(setEditDraft({ kind: "line-stop-add", a, b, stop_idx: null, scope: s }));
    },
    [scope, dispatch]
  );

  /** 3.2: `stop` off the line, its panel open for the Apply bar. */
  const removeFromLine = useCallback(
    (stop: LineStopRef) => {
      const s = scope();
      if (!s || !route) return;
      dispatch(openExplorerPanel({ item: { kind: "stop", stop }, fromRoute: route.route_id }));
      dispatch(setEditDraft({ kind: "line-stop-remove", stop_idx: stop.stop_idx, scope: s }));
    },
    [scope, route, dispatch]
  );

  return { insertBetween, removeFromLine, ready: !!route && !!drawing };
}
