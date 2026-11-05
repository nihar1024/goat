/**
 * The Apply bar (spec 01, Interaction model; boards 18, 23, 29): where every
 * edit ends, at the foot of the right panel. What it takes with it (a
 * delete's card), its ≈ cost; Cancel, and the
 * edit's own action, greyed out while it is refused (why is said once, in a
 * toast: useDraftEdit).
 * What else an edit changes is the panel's to show, in sections of its own
 * kind (a stop's delete card).
 */
import { Box, Button, Stack, Typography, alpha } from "@mui/material";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import type { DraftEdit } from "@/hooks/explorer/useDraftEdit";

import { PX, SectionHeader } from "@/components/explorer/SectionHeader";

export function ApplyBar({ edit, impact }: { edit: DraftEdit; impact?: ReactNode }) {
  const { t } = useTranslation("common");
  const { built, bar, applying } = edit;
  const nothing = built?.ok ? !built.rows.sql.length : true;

  return (
    // Less above than below: the first section header's own row (32 px)
    // already sets its name off the divider.
    // Set off from the panel as the edits list's foot is: a stronger line
    // over it and the grey of a confirmation.
    <Box
      sx={{
        px: PX,
        pt: "4px",
        pb: "12px",
        borderTop: 1,
        borderColor: (theme) => alpha(theme.palette.text.primary, 0.24),
        bgcolor: "action.hover",
        flexShrink: 0,
      }}>
      {/* What the edit takes with it, where it has a card for it. */}
      {impact}
      {/* As the operating cost card: its coins, and the change a year in
          the card's step figures. */}
      <Box>
        <SectionHeader icon={ICON_NAME.COINS} label={t("explorer_operating_cost")} px={0} />
        {bar?.costs ? (
          <Stack direction="row" alignItems="center" spacing={1} sx={{ minHeight: 24 }}>
            <Typography variant="caption" color="text.secondary" sx={{ flex: 1, minWidth: 0 }}>
              {t("explorer_cost_change")}
            </Typography>
            <Typography
              fontWeight="bold"
              noWrap
              sx={{ fontSize: 14, lineHeight: 1.2, fontVariantNumeric: "tabular-nums" }}>
              {bar.cost}
            </Typography>
          </Stack>
        ) : (
          // No change, not known, or still being worked out: said as the
          // sections' empty lines are.
          <Typography variant="caption" color="text.secondary" display="block">
            {bar?.cost ?? "…"}
          </Typography>
        )}
      </Box>
      {/* The cost set off from the buttons by a line across the panel, as
          the bar is from the panel above it. */}
      <Box sx={{ mx: -PX, mt: "12px", borderTop: 1, borderColor: "divider" }} />
      <Stack direction="row" justifyContent="flex-end" alignItems="center" spacing={1} sx={{ mt: "12px" }}>
        {/* As the dialogs' footer: Cancel in words, the action filled; both
            in the buttons' one size and weight, as the panel's others. */}
        <Button
          size="small"
          variant="text"
          onClick={edit.cancel}
          sx={{
            borderRadius: "16px",
            px: 1.5,
            fontWeight: 700,
            textTransform: "none",
            color: "text.secondary",
          }}>
          {t("cancel")}
        </Button>
        <Button
          size="small"
          variant="contained"
          color={bar?.danger ? "error" : "primary"}
          disabled={!built?.ok || nothing || applying}
          onClick={() => void edit.apply()}
          sx={{ borderRadius: "16px", px: 1.5, fontWeight: 700, textTransform: "none" }}>
          {bar?.action ?? t("apply")}
        </Button>
      </Stack>
    </Box>
  );
}
