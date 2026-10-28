/**
 * The edit bar's keys (board 17), while the Explorer is open for an editor:
 * V for Select, Ctrl/⌘+Z to undo, Ctrl/⌘+Shift+Z or Ctrl+Y to redo; Esc back
 * to Select from another tool. Never
 * while typing, nor while a dialog, the change list or a handler that used
 * the key (the strip's zoom) has it; the creating tools' letters (S, R, A)
 * come with the tools.
 */
import { useEffect } from "react";
import { useStore } from "react-redux";

import type { RootState } from "@/lib/store";
import { setEditTool } from "@/lib/store/explorer/slice";

import { useAppDispatch } from "@/hooks/store/ContextHooks";

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function useEditShortcuts(
  enabled: boolean,
  actions: { undo: () => Promise<void>; redo: () => Promise<void> }
): void {
  const dispatch = useAppDispatch();
  const store = useStore<RootState>();
  const { undo, redo } = actions;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || typing(e.target)) return;
      const explorer = store.getState().explorer;
      const edit = explorer.edit;
      // A dialog, the change list or the settings own the keys meanwhile.
      if (edit.exit || edit.listOpen || explorer.settingsTab) return;
      const key = e.key.toLowerCase();
      const mod = e.metaKey || e.ctrlKey;
      if (mod && key === "z") {
        e.preventDefault();
        void (e.shiftKey ? redo() : undo());
      } else if (mod && key === "y" && !e.metaKey) {
        e.preventDefault();
        void redo();
      } else if (!mod && !e.altKey && key === "v") {
        dispatch(setEditTool("select"));
      } else if (key === "escape") {
        // Another tool: back to Select.
        if (edit.tool !== "select") dispatch(setEditTool("select"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, undo, redo, dispatch, store]);
}
