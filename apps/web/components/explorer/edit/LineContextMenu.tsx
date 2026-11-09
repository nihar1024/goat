/**
 * A right click on the selected line, while editing: on one of its stops,
 * the stop's edits on the line (as its row's menu in the Stops tab has
 * them), and at either end of the line, the line run on from it; on the
 * line between two stops, a stop added there (as the Stops tab's hover
 * action between them). Along the variant picked, else the
 * direction's main pattern, as a click on the line selects.
 */
import { Popover } from "@mui/material";
import type { TFunction } from "i18next";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import { pathAt } from "@/lib/explorer/derive/path";
import { shownPattern } from "@/lib/explorer/directionChoice";
import type { LineEnd } from "@/lib/explorer/edit/ops/extendLine";
import { sqlNumber } from "@/lib/explorer/edit/sql";
import { closeExplorerLineMenu } from "@/lib/store/explorer/slice";

import { type LineStopRef, useLineStopEdits } from "@/hooks/explorer/useLineStopEdits";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { PopperMenuContent, type PopperMenuItem } from "@/components/common/PopperMenu";
import { useExplorer } from "@/components/explorer/ExplorerContext";

/** A stop's edits on its line, in its row's menu and on the map alike: at
 * either end (`end`), the line extended from it too. */
export function lineStopMenu(t: TFunction, end?: LineEnd): PopperMenuItem[] {
  return [
    ...(end ? [{ id: `extend-${end}`, label: t("explorer_extend_line"), icon: ICON_NAME.PLUS }] : []),
    {
      id: "remove",
      label: t("explorer_remove_stop_from_line"),
      icon: ICON_NAME.MINUS,
      color: "error.main",
    },
  ];
}

/** The line between two stops: a stop added there (as the Stops tab's +
 * between them is named). */
function segmentMenu(t: TFunction): PopperMenuItem[] {
  return [{ id: "insert", label: t("explorer_add_stop_to_line"), icon: ICON_NAME.PLUS }];
}

type Resolved =
  | { kind: "stop"; stop: LineStopRef; items: PopperMenuItem[] }
  | { kind: "segment"; a: number; b: number; items: PopperMenuItem[] };

export function LineContextMenu() {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { db } = useExplorer();
  const at = useAppSelector((s) => s.explorer.lineMenu);
  const drawing = useAppSelector((s) => s.explorer.drawing);
  const choice = useAppSelector((s) => s.explorer.pattern);
  const { insertBetween, removeFromLine, extend, cutLine } = useLineStopEdits();
  const [resolved, setResolved] = useState<Resolved | null>(null);

  useEffect(() => {
    setResolved(null);
    if (!at || !db || !drawing) return;
    const pattern = shownPattern(choice, drawing.directions);
    if (pattern === null) return;
    let current = true;
    const close = () => current && dispatch(closeExplorerLineMenu());
    (async () => {
      const [p] = await db.all<{ stops: ArrayLike<number> }>(
        `SELECT stops FROM patterns WHERE pattern_idx = ${sqlNumber(pattern)}`
      );
      const stops = p ? Array.from(p.stops) : [];
      // On a stop of the line shown: its edits.
      if (at.stop_idx !== null && stops.includes(at.stop_idx)) {
        const [row] = await db.all<LineStopRef>(`
          SELECT s.stop_idx, COALESCE(p.name, s.name, s.stop_id) AS name, s.lat, s.lon
          FROM stops s LEFT JOIN stops p ON p.stop_idx = s.parent_idx WHERE s.stop_idx = ${sqlNumber(at.stop_idx)}`);
        if (!current) return;
        // At either end of the line shown: extended from there too. Its
        // ends are also where the line is cut back to: offered where they cut
        // something (not past the line's own first or last stop).
        const end: LineEnd | undefined =
          at.stop_idx === stops[stops.length - 1] ? "end" : at.stop_idx === stops[0] ? "start" : undefined;
        const i = stops.indexOf(at.stop_idx);
        if (row)
          setResolved({
            kind: "stop",
            stop: row,
            items: [
              ...lineStopMenu(t, end),
              ...(i < stops.length - 1
                ? [
                    {
                      id: "end",
                      label: t("explorer_line_cut_end"),
                      icon: ICON_NAME.CHEVRON_RIGHT,
                      group: "cut",
                    },
                  ]
                : []),
              ...(i > 0
                ? [
                    {
                      id: "start",
                      label: t("explorer_line_cut_start"),
                      icon: ICON_NAME.CHEVRON_LEFT,
                      group: "cut",
                    },
                  ]
                : []),
            ],
          });
        else close();
        return;
      }
      // On the line: between the two stops around the click.
      const path = await pathAt(db, pattern, at.lon, at.lat);
      if (!current) return;
      if (path && stops[path.from_i] !== undefined && stops[path.to_i] !== undefined)
        setResolved({ kind: "segment", a: stops[path.from_i], b: stops[path.to_i], items: segmentMenu(t) });
      else close();
    })().catch(close);
    return () => {
      current = false;
    };
  }, [at, db, drawing, choice, t, dispatch]);

  const close = () => dispatch(closeExplorerLineMenu());
  return (
    <Popover
      open={!!at && !!resolved}
      // Esc closes it after the keys' other listeners have seen it open,
      // so the editor's Esc does not also let go of the selection.
      onClose={(_e, reason) => (reason === "escapeKeyDown" ? setTimeout(close) : close())}
      anchorReference="anchorPosition"
      anchorPosition={at ? { top: at.y, left: at.x } : undefined}
      // The menu's own paper, as PopperMenu draws it.
      slotProps={{ paper: { sx: { boxShadow: "none", bgcolor: "transparent", overflow: "visible" } } }}>
      {resolved && (
        <PopperMenuContent
          menuItems={resolved.items}
          onPick={(item) => {
            close();
            if (resolved.kind === "segment") insertBetween(resolved.a, resolved.b);
            else if (item.id === "extend-end" || item.id === "extend-start")
              extend(resolved.stop.stop_idx, item.id === "extend-end" ? "end" : "start");
            else if (item.id === "end" || item.id === "start") cutLine(resolved.stop, item.id);
            else removeFromLine(resolved.stop);
          }}
        />
      )}
    </Popover>
  );
}
