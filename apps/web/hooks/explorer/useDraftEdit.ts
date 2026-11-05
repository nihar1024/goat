/**
 * The edit being made (the draft), as the Apply bar shows it: built into a
 * change against the snapshot as it is now, rebuilt as the draft changes or
 * an undo changes the snapshot under it, its ≈ cost previewed (applied out
 * of sight and rolled back, EditSession.preview), worded, and applied on
 * Apply.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import type { SqlRunner } from "@/lib/explorer/db/types";
import { tripsAnnualFigures } from "@/lib/explorer/derive/cost";
import { type DraftPathKind, draftPathsStore } from "@/lib/explorer/edit/draftStore";
import type { EditDraft, StopValues } from "@/lib/explorer/edit/drafts";
import { type DeleteStopFacts, deleteStop } from "@/lib/explorer/edit/ops/deleteStop";
import { type MoveStopFacts, type Router, moveStop } from "@/lib/explorer/edit/ops/moveStop";
import { locationKind } from "@/lib/explorer/edit/ops/stopRules";
import {
  type NewStopFacts,
  type StopDetailsFacts,
  createStop,
  editStopDetails,
} from "@/lib/explorer/edit/ops/stops";
import type { Built, Check } from "@/lib/explorer/edit/ops/types";
import { carRoads } from "@/lib/explorer/edit/roads";
import type { ChangeSummary } from "@/lib/explorer/edit/types";
import { rateFor } from "@/lib/explorer/settings";
import {
  closeExplorerPanel,
  openExplorerPanel,
  setEditDraft,
  setEditTool,
  setExplorerStopTab,
} from "@/lib/store/explorer/slice";

import { useEditActions } from "@/hooks/explorer/useEditActions";
import { useEdition } from "@/hooks/explorer/useEdition";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";
import { costChange } from "@/components/explorer/edit/costWords";

type T = (key: string, options?: Record<string, unknown>) => string;

/** A draft built: by its kind, with the facts its operation found. */
export type Building =
  | { kind: "stop-details"; built: Built<StopDetailsFacts> }
  | { kind: "stop-new"; built: Built<NewStopFacts> }
  | { kind: "stop-delete"; built: Built<DeleteStopFacts> }
  | { kind: "stop-move"; built: Built<MoveStopFacts> };

/** What the Apply bar says of the draft. */
export interface BarWords {
  /** Its ≈ cost, or that it costs nothing; null while it is worked out. */
  cost: string | null;
  /** It changes what the network costs. */
  costs?: boolean;
  /** The primary button, and whether it removes something. */
  action: string;
  danger?: boolean;
}

export interface DraftEdit {
  draft: EditDraft;
  /** Null while it is being built. */
  building: Building | null;
  built: Building["built"] | null;
  /** The change's name and what else it changes, as the change list keeps
   * them; and what the Apply bar says. */
  words: Pick<ChangeSummary, "label" | "impact"> | null;
  bar: BarWords | null;
  applying: boolean;
  apply: () => Promise<void>;
  cancel: () => void;
}

/** The draft edit, for the panel parts that show what it changes. */
export const DraftEditContext = createContext<DraftEdit | null>(null);
export const useDraftEditShown = () => useContext(DraftEditContext);

let ids = 0;

export function useDraftEdit(): DraftEdit | null {
  const { t, i18n } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { db, session, shapeDistUnit, settings, window } = useExplorer();
  const edition = useEdition(db);
  const draft = useAppSelector((s) => s.explorer.edit.draft);
  // With Snap on, a moved stop's lines follow the streets.
  const snap = useAppSelector((s) => s.explorer.edit.snap);
  const { apply: applyChange } = useEditActions();
  const [building, setBuilding] = useState<{ draft: EditDraft; building: Building } | null>(null);
  // The change in annual cost, for the draft built (undefined: not yet).
  const [cost, setCost] = useState<{ draft: EditDraft; building: Building; value: number | null } | null>(
    null
  );
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!db || !draft) return;
    let current = true;
    const run = (roads?: Router) =>
      build(db, draft, shapeDistUnit, roads)
        .then((b) => current && setBuilding({ draft, building: b }))
        .catch(() => current && setBuilding(null));
    // A moved stop's lines along the streets (Snap), built once, when the
    // stop rests: the router answers one request a second, and asking at
    // every step of a drag queued the drop's own request behind the whole
    // drag's. Not drawn straight first and then again: one path, once.
    if (snap && draft.kind === "stop-move") {
      // Once this build is stale, its remaining stretches ask no more of
      // the router: its one request a second goes to the drop that counts.
      const roads: Router = (waypoints) => (current ? carRoads(waypoints) : Promise.resolve(null));
      const routed = setTimeout(() => void run(roads), ROUTE_AFTER_MS);
      return () => {
        current = false;
        clearTimeout(routed);
      };
    }
    // Anything else at once: the draft changes at each step of a drag.
    void run();
    return () => {
      current = false;
    };
  }, [db, draft, edition, shapeDistUnit, snap]);

  const now = building && building.draft === draft ? building.building : null;

  // Why it is refused, and its notices, said once as it is built, as
  // toasts: worth knowing, not worth keeping beside the edit. One toast a
  // finding, not one a build. A refusal on a form field is said on it.
  useEffect(() => {
    if (!now) return;
    const words = (c: Check) =>
      t(`explorer_check_${c.code}`, { ...c.params, interpolation: { escapeValue: false } });
    if (!now.built.ok && !now.built.refused.field)
      toast.error(words(now.built.refused), { toastId: now.built.refused.code });
    for (const c of now.built.checks)
      if (c.severity === "notice") toast.warning(words(c), { toastId: c.code });
  }, [now, t]);
  // While the draft is rebuilt (each key typed, each step of a drag), what
  // was built for the same edit stays shown: the Apply bar and the map keep
  // their words and paths instead of blinking empty between builds.
  const shown = now ?? (building && draft && sameEdit(building.draft, draft) ? building.building : null);

  // The paths a stop being moved would take, for the map: each new one, and
  // the one it replaces in its two parts. Only once built for where the stop
  // is now, not what was built for where it was.
  useEffect(() => {
    const paths = now?.kind === "stop-move" && now.built.ok ? now.built.facts.paths : null;
    const line = (coordinates: [number, number][], kind: DraftPathKind, color: string) => ({
      type: "Feature" as const,
      geometry: { type: "LineString" as const, coordinates },
      properties: { kind, color },
    });
    draftPathsStore.set(
      paths && {
        type: "FeatureCollection",
        features: paths.flatMap((p) => [
          ...(p.old?.kept ?? []).map((c) => line(c, "kept", p.color)),
          ...(p.old?.replaced ?? []).map((c) => line(c, "replaced", p.color)),
          // Dotted only where it is drawn anew: the rest runs as it did.
          ...p.drawn.filter((c) => c.length > 1).map((c) => line(c, "new", p.color)),
        ]),
      },
      paths?.flatMap((p) => (p.replaces ? [p.replaces] : [])) ?? []
    );
  }, [now]);
  useEffect(() => () => draftPathsStore.set(null), []);

  // What the trips it changes cost a year, before and after it.
  useEffect(() => {
    if (!now || !session || !window) return;
    const trips = tripsOf(now);
    if (!now.built.ok || !trips?.length) return;
    let current = true;
    const where = `trip_idx IN (${trips.join(", ")})`;
    session
      .preview(now.built.rows.sql, (d) =>
        tripsAnnualFigures(d, where, window, (a, type) => rateFor(settings, a, type))
      )
      .then(
        (seen) =>
          current &&
          draft &&
          setCost({ draft, building: now, value: seen ? seen.after.cost - seen.before.cost : null })
      )
      .catch(() => current && draft && setCost({ draft, building: now, value: null }));
    return () => {
      current = false;
    };
  }, [now, draft, session, window, settings]);

  // Likewise the last cost of the same edit, until the new one is known.
  const priced = !tripsOf(shown)?.length
    ? 0
    : cost && (cost.building === shown || (draft && sameEdit(cost.draft, draft)))
      ? cost.value
      : undefined;
  const said = shown ? wordsFor(shown, t) : null;
  const bar =
    said &&
    ({
      ...said.bar,
      cost:
        priced === undefined
          ? null
          : priced === null
            ? t("explorer_cost_unknown")
            : costChange(priced, i18n.language, settings.currency, t),
      costs: typeof priced === "number" && Math.abs(priced) >= 0.5,
    } satisfies BarWords);

  const apply = useCallback(async () => {
    if (!now?.built.ok || !said || !session || !now.built.rows.sql.length) return;
    setApplying(true);
    try {
      await applyChange({
        id: `e${Date.now()}-${ids++}`,
        ...said.words,
        cost: typeof priced === "number" && tripsOf(now)?.length ? priced : undefined,
        ...now.built.rows,
      });
      // The Stop tool is one-shot: back to Select, the new stop picked.
      if (now.kind === "stop-new" && draft?.kind === "stop-new") {
        dispatch(setEditTool("select"));
        dispatch(
          openExplorerPanel({
            item: {
              kind: "stop",
              stop: {
                stop_idx: now.built.facts.stop_idx,
                name: now.built.facts.name,
                lon: draft.lon,
                lat: draft.lat,
              },
            },
          })
        );
        dispatch(setExplorerStopTab("properties"));
      }
      // A stop deleted has nothing left to show.
      if (now.kind === "stop-delete") dispatch(closeExplorerPanel());
    } finally {
      setApplying(false);
    }
  }, [now, said, priced, session, applyChange, dispatch, draft]);
  const cancel = useCallback(() => dispatch(setEditDraft(null)), [dispatch]);

  if (!draft) return null;
  return {
    draft,
    building: shown,
    built: shown?.built ?? null,
    words: said?.words ?? null,
    bar,
    applying,
    apply,
    cancel,
  };
}

/** How long a moved stop rests before its lines are routed along the streets. */
const ROUTE_AFTER_MS = 500;

/** The trips an edit changes, where it changes what they cost. */
function tripsOf(b: Building | null): number[] | null {
  return b?.kind === "stop-delete" || b?.kind === "stop-move" ? (b.built.facts?.trip_idxs ?? null) : null;
}

async function build(
  db: SqlRunner,
  draft: EditDraft,
  shapeDistUnit: string | null,
  roads?: Router
): Promise<Building> {
  switch (draft.kind) {
    case "stop-details":
      return { kind: draft.kind, built: await editStopDetails(db, draft.stop_idx, draft.values) };
    case "stop-new":
      return {
        kind: draft.kind,
        built: await createStop(db, draft.lon, draft.lat, draft.values, draft.stop_id ?? ""),
      };
    case "stop-delete":
      return { kind: draft.kind, built: await deleteStop(db, draft.stop_idx, shapeDistUnit) };
    case "stop-move":
      return {
        kind: draft.kind,
        built: await moveStop(db, draft.stop_idx, [draft.lon, draft.lat], shapeDistUnit, roads),
      };
  }
}

/** The same edit of the same thing, whatever its values now. */
function sameEdit(a: EditDraft, b: EditDraft): boolean {
  if (a.kind !== b.kind) return false;
  return !("stop_idx" in a) || !("stop_idx" in b) || a.stop_idx === b.stop_idx;
}

function wordsFor(
  b: Building,
  t: T
): { words: Pick<ChangeSummary, "label" | "impact">; bar: Omit<BarWords, "cost"> } {
  const raw = { interpolation: { escapeValue: false } };
  switch (b.kind) {
    case "stop-details": {
      const facts = b.built.facts;
      const changed = facts?.changed ?? [];
      const field = (k: keyof StopValues) => t(`explorer_stop_field_${k}`);
      const words =
        facts && changed.length === 1 && changed[0] === "name"
          ? { label: t("explorer_edit_stop_renamed", { from: facts.from.name, to: facts.to.name, ...raw }) }
          : {
              label: t("explorer_edit_stop_details", { name: facts?.to.name || facts?.from.name, ...raw }),
              impact: changed.map(field).join(" · "),
            };
      return {
        words,
        bar: { action: t("apply") },
      };
    }
    case "stop-new":
      return {
        words: {
          label: t(`explorer_edit_${locationKind(b.built.facts?.location_type)}_created`, {
            name: b.built.facts?.name ?? "",
            ...raw,
          }),
          impact:
            locationKind(b.built.facts?.location_type) === "stop" ? t("explorer_not_served") : undefined,
        },
        bar: { action: t(`explorer_create_${locationKind(b.built.facts?.location_type)}`) },
      };
    case "stop-delete": {
      const f = b.built.facts;
      const kind = locationKind(f?.location_type);
      const impact =
        kind === "station"
          ? [
              f?.platforms ? t("explorer_platforms_deleted", { count: f.platforms }) : null,
              f && f.entrances + f.nodes
                ? t("explorer_entrances_deleted", { count: f.entrances + f.nodes })
                : null,
              f?.trips ? t("explorer_trips", { count: f.trips }) : null,
              f?.trips ? t("explorer_lines_count", { count: f.routes.length }) : null,
            ]
              .filter(Boolean)
              .join(" · ") || undefined
          : kind === "entrance"
            ? undefined
            : f?.trips
              ? [
                  t("explorer_trips", { count: f.trips }),
                  t("explorer_lines_count", { count: f.routes.length }),
                ].join(" · ")
              : t("explorer_not_served");
      return {
        words: { label: t(`explorer_edit_${kind}_deleted`, { name: f?.name ?? "", ...raw }), impact },
        bar: { action: t(`explorer_delete_${kind}`), danger: true },
      };
    }
    case "stop-move": {
      const f = b.built.facts;
      const moved = t("explorer_moved_m", { metres: Math.round(f?.metres ?? 0) });
      const paths = f?.paths.length ? t("explorer_paths_redrawn", { count: f.paths.length }) : null;
      const impact = [moved, paths, f?.trips ? t("explorer_times_kept", { count: f.trips }) : null]
        .filter(Boolean)
        .join(" · ");
      return {
        words: { label: t("explorer_edit_stop_moved", { name: f?.name ?? "", ...raw }), impact },
        bar: {
          action: t("apply"),
        },
      };
    }
  }
}
