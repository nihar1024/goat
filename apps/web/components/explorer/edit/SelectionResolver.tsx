/**
 * Works out, with the snapshot, the path a click on the picked direction's
 * line selects — the map's layers have no database — and hands the map its
 * line, the stretch between the two stops around the click. A trip draws
 * nothing of its own on the map (board 24): its path is its pattern's.
 *
 * For an editor only: these levels are where edits apply (reroute, insert a
 * stop, a trip's times), so a user who cannot edit clicks as before.
 */
import { useEffect } from "react";

import { pathAt } from "@/lib/explorer/derive/path";
import { selectionStore } from "@/lib/explorer/selectionStore";
import { setExplorerPath } from "@/lib/store/explorer/slice";

import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";

export function SelectionResolver() {
  const { db, session } = useExplorer();
  const dispatch = useAppDispatch();
  const click = useAppSelector((s) => s.explorer.pathClick);
  const drawing = useAppSelector((s) => s.explorer.drawing);
  const pattern = useAppSelector((s) => s.explorer.pattern);
  const path = useAppSelector((s) => s.explorer.path);

  // A click on the picked direction's line: the path it falls on, along
  // the variant picked, else the direction's main pattern.
  useEffect(() => {
    if (!click || !session || !db || !drawing) return;
    const direction = drawing.directions.find((d) => d.key === pattern?.direction) ?? drawing.directions[0];
    const pattern_idx = pattern?.pattern_idx ?? direction?.key;
    if (pattern_idx === undefined) return;
    let current = true;
    pathAt(db, pattern_idx, click.lon, click.lat)
      .then((found) => {
        if (!current) return;
        if (!found) {
          dispatch(setExplorerPath(null));
          return;
        }
        const { line, ...selected } = found;
        selectionStore.set([{ type: "LineString", coordinates: line }]);
        dispatch(setExplorerPath(selected));
      })
      .catch(() => current && dispatch(setExplorerPath(null)));
    return () => {
      current = false;
    };
    // Each click once, as it comes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [click?.n]);

  // The path let go of (another direction, line, trip or stop): its line goes.
  useEffect(() => {
    if (!path) selectionStore.set(null);
  }, [path]);

  useEffect(() => () => selectionStore.set(null), []);
  return null;
}
