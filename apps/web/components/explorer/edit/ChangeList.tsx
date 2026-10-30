/**
 * The change list (board 28), under the edit bar's count: every change of
 * the session, newest first, each with what it did and its cost; Undo on the
 * newest only, since undo goes back in order (03-validation-spec § 6).
 * Save, greyed out until there are edits, saves them and closes the
 * Explorer, as the bottom bar's Save and exit does.
 *
 * Laid out as the Explorer's panels are: a section header with its count,
 * rows on the same left edge, the panels' surface.
 */
import LoadingButton from "@mui/lab/LoadingButton";
import { Box, Button, Popover, Stack, Typography, alpha } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { setChangeListOpen } from "@/lib/store/explorer/slice";

import { useExplorerSave } from "@/hooks/explorer/useExplorerSave";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";
import { PX } from "@/components/explorer/SectionHeader";
import { costChange } from "@/components/explorer/edit/costWords";

export function ChangeList({ anchor, undo }: { anchor: HTMLElement | null; undo: () => Promise<void> }) {
  const { t, i18n } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { save } = useExplorerSave();
  const saving = useAppSelector((s) => s.explorer.edit.exit === "saving");
  const { settings } = useExplorer();
  const open = useAppSelector((s) => s.explorer.edit.listOpen);
  const changes = useAppSelector((s) => s.explorer.edit.changes);
  const newest = [...changes].reverse();
  const costs = changes.filter((c) => c.cost !== undefined);
  const total = costs.reduce((sum, c) => sum + (c.cost ?? 0), 0);
  const cost = (value: number) => costChange(value, i18n.language, settings.currency, t);

  return (
    <Popover
      open={open && !!anchor}
      anchorEl={anchor}
      onClose={() => dispatch(setChangeListOpen(false))}
      // By the count's left edge, which stays put: its right edge moves with
      // its words ("1 edit", "No edits"), and the list would move with it.
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          // The Explorer's floating surface (FloatingPanel).
          sx: {
            // 8 px clear of the bar: the pill it hangs from sits 4 px inside it.
            mt: "12px",
            width: 340,
            borderRadius: "1rem",
            bgcolor: (theme) => alpha(theme.palette.background.paper, 0.9),
            backdropFilter: "blur(10px)",
            boxShadow: "rgba(0, 0, 0, 0.2) 0px 0px 10px",
          },
        },
      }}>
      {/* As a section header of the panels: icon, title, count. */}
      <Stack direction="row" alignItems="center" sx={{ px: PX, minHeight: 40, columnGap: "10px" }}>
        <Icon iconName={ICON_NAME.EDIT} style={{ fontSize: 14 }} htmlColor="inherit" />
        <Typography variant="body2" fontWeight="bold" noWrap sx={{ flex: 1 }}>
          {t("explorer_edits_title")}
        </Typography>
        {changes.length > 0 && (
          <Box
            component="span"
            sx={{
              px: 1,
              py: 0.25,
              borderRadius: 1,
              bgcolor: "action.hover",
              color: "text.secondary",
              fontSize: 12,
              fontWeight: 600,
            }}>
            {changes.length}
          </Box>
        )}
      </Stack>
      {newest.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ px: PX, py: "24px", textAlign: "center", borderTop: 1, borderColor: "divider" }}>
          {t("explorer_edits_empty")}
        </Typography>
      ) : (
        <Box sx={{ maxHeight: 320, overflowY: "auto" }}>
          {newest.map((c, i) => (
            <Stack
              key={c.id}
              direction="row"
              spacing={1.25}
              alignItems="center"
              sx={{ px: PX, py: 1.25, borderTop: 1, borderColor: "divider" }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} color="text.primary" noWrap title={c.label}>
                  {c.label}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" noWrap>
                  {[c.impact, c.cost !== undefined ? cost(c.cost) : null].filter(Boolean).join(" · ") ||
                    t("explorer_change_no_cost")}
                </Typography>
              </Box>
              {i === 0 && (
                // Quiet, as the row's own words: an aside to the edit, not an
                // action to compete with Save.
                <Button
                  size="small"
                  variant="text"
                  color="inherit"
                  onClick={() => void undo()}
                  startIcon={<Icon iconName={ICON_NAME.UNDO} style={{ fontSize: 10 }} htmlColor="inherit" />}
                  sx={{
                    flexShrink: 0,
                    borderRadius: "16px",
                    px: 1,
                    fontSize: 12,
                    fontWeight: 600,
                    textTransform: "none",
                    color: "text.secondary",
                    "& .MuiButton-startIcon": { mr: 0.75 },
                    "&:hover": { color: "text.primary" },
                  }}>
                  {t("undo")}
                </Button>
              )}
            </Stack>
          ))}
        </Box>
      )}
      {/* A border, not a Divider: the theme gives a Divider margins. */}
      <Stack
        direction="row"
        alignItems="center"
        spacing={1.5}
        sx={{ px: PX, py: 1.5, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="caption" color="text.secondary" sx={{ flex: 1, minWidth: 0 }} noWrap>
          {costs.length > 0 && cost(total)}
        </Typography>
        {/* Saves and stays: the saving shown on the button, the list open
            until it is done (and then empty). */}
        <LoadingButton
          variant="contained"
          size="small"
          loading={saving}
          loadingPosition="start"
          disabled={!changes.length}
          onClick={() => void save()}
          startIcon={<Icon iconName={ICON_NAME.SAVE} style={{ fontSize: 12 }} htmlColor="inherit" />}
          sx={{ borderRadius: "16px", px: 1.5, fontWeight: 700, textTransform: "none", flexShrink: 0 }}>
          {t("explorer_save_edits")}
        </LoadingButton>
      </Stack>
    </Popover>
  );
}
