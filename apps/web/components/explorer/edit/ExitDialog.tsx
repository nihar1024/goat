/**
 * Leaving the Explorer with changes (02-panel-behaviour-spec › Exit
 * Explorer): "Save edits to <bundle>?", with what changed per table and the
 * reminder that saving updates the bundle for everyone in the project. It
 * asks when the Explorer is left another way with changes, and comes back,
 * saying why, when a Save and exit does not go through.
 * Discard changes (red, left) drops them; Keep editing (or Esc, or a click
 * outside) stays; Save and exit writes them into the bundle and goes on with
 * whatever was leaving — closing the Explorer, another bundle's, another view.
 */
import { Alert, Box, Button, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import { takeLeave } from "@/lib/explorer/edit/leave";
import { setExitState } from "@/lib/store/explorer/slice";

import { useExplorerSave } from "@/hooks/explorer/useExplorerSave";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import AppDialog, { AppDialogFooter } from "@/components/common/AppDialog";
import { useExplorer } from "@/components/explorer/ExplorerContext";

export function ExitDialog() {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { session } = useExplorer();
  const { save, discard } = useExplorerSave();
  const exit = useAppSelector((s) => s.explorer.edit.exit);
  const problem = useAppSelector((s) => s.explorer.edit.saveProblem);
  const changes = useAppSelector((s) => s.explorer.edit.changes);
  const name = useAppSelector((s) => s.explorer.bundleName) ?? "";
  const saving = exit === "saving";

  // Rows per table, as the save will write them.
  const perTable = new Map<string, number>();
  for (const op of session?.changeset() ?? []) perTable.set(op.role, (perTable.get(op.role) ?? 0) + 1);

  const keepEditing = () => {
    if (saving) return;
    takeLeave();
    dispatch(setExitState(null));
  };

  return (
    <AppDialog
      open={exit !== null}
      onClose={keepEditing}
      icon={ICON_NAME.SAVE}
      title={t("explorer_exit_title", { name })}
      closeDisabled={saving}
      maxWidth={480}
      footer={
        <AppDialogFooter
          extra={
            <Button color="error" disabled={saving} onClick={() => void discard()}>
              <Typography variant="body2" fontWeight="bold" color="inherit">
                {t("explorer_discard_edits")}
              </Typography>
            </Button>
          }
          cancelLabel={t("explorer_keep_editing")}
          onCancel={keepEditing}
          cancelDisabled={saving}
          primaryLabel={t("explorer_save_exit")}
          onPrimary={() => void save()}
          primaryLoading={saving}
        />
      }>
      <Stack spacing={2}>
        <Typography variant="body2">
          {t("explorer_exit_body", { count: changes.length })}
          {perTable.size > 0 &&
            ` · ${[...perTable].map(([role, n]) => `${t(`explorer_table_${role}`)} ${n}`).join(" · ")}`}
        </Typography>
        <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
          {changes.map((c) => (
            <Typography key={c.id} component="li" variant="body2">
              {c.label}
              {c.impact && (
                <Typography component="span" variant="body2" color="text.secondary">
                  {` · ${c.impact}`}
                </Typography>
              )}
            </Typography>
          ))}
        </Box>
        <Typography variant="body2" color="text.secondary">
          {t("explorer_exit_everyone")}
        </Typography>
        {problem && <Alert severity="error">{problem}</Alert>}
      </Stack>
    </AppDialog>
  );
}
