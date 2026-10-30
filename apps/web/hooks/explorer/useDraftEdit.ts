/**
 * The edit being made (the draft), as the Apply bar shows it: built into a
 * change against the snapshot as it is now, rebuilt as the draft changes or
 * an undo changes the snapshot under it, worded, and applied on Apply. A
 * stop made or described changes no trip: its ≈ cost is none.
 */
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { SqlRunner } from "@/lib/explorer/db/types";
import type { EditDraft, StopValues } from "@/lib/explorer/edit/drafts";
import { locationKind } from "@/lib/explorer/edit/ops/stopRules";
import {
  type NewStopFacts,
  type StopDetailsFacts,
  createStop,
  editStopDetails,
} from "@/lib/explorer/edit/ops/stops";
import type { Built } from "@/lib/explorer/edit/ops/types";
import type { ChangeSummary } from "@/lib/explorer/edit/types";
import { openExplorerPanel, setEditDraft, setEditTool, setExplorerStopTab } from "@/lib/store/explorer/slice";

import { useEditActions } from "@/hooks/explorer/useEditActions";
import { useEdition } from "@/hooks/explorer/useEdition";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";
import { costChange } from "@/components/explorer/edit/costWords";

type T = (key: string, options?: Record<string, unknown>) => string;

/** A draft built: by its kind, with the facts its operation found. */
export type Building =
  | { kind: "stop-details"; built: Built<StopDetailsFacts> }
  | { kind: "stop-new"; built: Built<NewStopFacts> };

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
  const { db, session, settings } = useExplorer();
  const edition = useEdition(db);
  const draft = useAppSelector((s) => s.explorer.edit.draft);
  const { apply: applyChange } = useEditActions();
  const [building, setBuilding] = useState<{ draft: EditDraft; building: Building } | null>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!db || !draft) return;
    let current = true;
    build(db, draft)
      .then((b) => current && setBuilding({ draft, building: b }))
      .catch(() => current && setBuilding(null));
    return () => {
      current = false;
    };
  }, [db, draft, edition]);

  const now = building && building.draft === draft ? building.building : null;
  // While the draft is rebuilt (each key typed, each step of a drag), what
  // was built for the same edit stays shown: the Apply bar and the map keep
  // their words instead of blinking empty between builds.
  const shown = now ?? (building && draft && sameEdit(building.draft, draft) ? building.building : null);

  const said = shown ? wordsFor(shown, t) : null;
  const bar =
    said &&
    ({
      ...said.bar,
      cost: costChange(0, i18n.language, settings.currency, t),
      costs: false,
    } satisfies BarWords);

  const apply = useCallback(async () => {
    if (!now?.built.ok || !said || !session || !now.built.rows.sql.length) return;
    setApplying(true);
    try {
      await applyChange({
        id: `e${Date.now()}-${ids++}`,
        ...said.words,
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
    } finally {
      setApplying(false);
    }
  }, [now, said, session, applyChange, dispatch, draft]);
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

async function build(db: SqlRunner, draft: EditDraft): Promise<Building> {
  switch (draft.kind) {
    case "stop-details":
      return { kind: draft.kind, built: await editStopDetails(db, draft.stop_idx, draft.values) };
    case "stop-new":
      return {
        kind: draft.kind,
        built: await createStop(db, draft.lon, draft.lat, draft.values, draft.stop_id ?? ""),
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
  }
}
