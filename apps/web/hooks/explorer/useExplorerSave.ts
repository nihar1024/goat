/**
 * Saving the editing session into its bundle, then going on with what was
 * leaving (lib/explorer/edit/leave.ts): Save and exit in the bottom bar and
 * in the exit dialog. A save that does not go through keeps the changes and
 * opens the dialog, saying why.
 */
import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { SaveConflictError, SaveRefusedError, saveExplorerChanges } from "@/lib/explorer/edit/api";
import { takeLeave } from "@/lib/explorer/edit/leave";
import { saveFailed, setExitState } from "@/lib/store/explorer/slice";

import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";

export function useExplorerSave() {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { session, revision } = useExplorer();
  const bundleId = useAppSelector((s) => s.explorer.bundleId);
  const name = useAppSelector((s) => s.explorer.bundleName) ?? "";

  /** Drop the session's changes and go on with what was leaving. */
  const finish = useCallback(async () => {
    await session?.clear();
    dispatch(setExitState(null));
    takeLeave()?.();
  }, [session, dispatch]);

  const save = useCallback(async () => {
    if (!session || !bundleId || revision === null) return;
    dispatch(setExitState("saving"));
    try {
      await saveExplorerChanges(bundleId, revision, session.changeset());
      toast.success(t("explorer_saved", { name }));
      await finish();
    } catch (error) {
      dispatch(
        saveFailed(
          error instanceof SaveConflictError
            ? t("explorer_save_conflict")
            : error instanceof SaveRefusedError
              ? t("explorer_save_refused")
              : t("explorer_save_failed", { message: String((error as Error).message ?? error) })
        )
      );
    }
  }, [session, bundleId, revision, name, t, dispatch, finish]);

  return { save, discard: finish };
}
