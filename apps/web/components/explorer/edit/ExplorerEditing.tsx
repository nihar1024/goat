/**
 * Editing in the Explorer, for a user who may write the bundle: the edit
 * bar on the Explorer tab (on the Layers tab it is hidden: editing lives in
 * the Explorer, board 17), its keys, the exit dialog wherever leaving starts,
 * and the browser's warning before a reload drops unsaved changes.
 */
import { useEditActions } from "@/hooks/explorer/useEditActions";
import { useEditShortcuts } from "@/hooks/explorer/useEditShortcuts";
import { useLeaveWarning } from "@/hooks/explorer/useLeaveWarning";
import { useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";
import { EditBar } from "@/components/explorer/edit/EditBar";
import { ExitDialog } from "@/components/explorer/edit/ExitDialog";

export function ExplorerEditing({ compact, barHidden }: { compact: boolean; barHidden: boolean }) {
  const { session } = useExplorer();
  const onExplorerTab = useAppSelector((s) => s.explorer.leftTab === "explorer");
  const unsaved = useAppSelector((s) => s.explorer.edit.changes.length > 0);
  const actions = useEditActions();
  useEditShortcuts(!!session, actions);
  useLeaveWarning(unsaved);
  return (
    <>
      {session && onExplorerTab && !barHidden && (
        <EditBar compact={compact} undo={actions.undo} redo={actions.redo} />
      )}
      <ExitDialog />
    </>
  );
}
