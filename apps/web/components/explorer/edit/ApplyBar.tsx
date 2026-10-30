/**
 * The Apply bar (spec 01, Interaction model; boards 18, 23, 29): where every
 * edit ends, at the foot of the right panel. Its ≈ cost, its warnings, or
 * why it is not possible; Cancel, and the edit's own action.
 * What else an edit changes is the panel's to show, in sections of its own
 * kind (a stop's delete card).
 */
import { Box, Button, Stack, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import type { Check } from "@/lib/explorer/edit/ops/types";

import type { DraftEdit } from "@/hooks/explorer/useDraftEdit";

import { PX, SectionHeader } from "@/components/explorer/SectionHeader";

/** A check in words, by its notice code. */
export function checkWords(check: Check, t: (key: string, options?: Record<string, unknown>) => string) {
  return t(`explorer_check_${check.code}`, { ...check.params, interpolation: { escapeValue: false } });
}

export function ApplyBar({ edit }: { edit: DraftEdit }) {
  const { t } = useTranslation("common");
  const { built, bar, applying } = edit;
  const refused = built && !built.ok ? built.refused : null;
  const warnings = built ? built.checks.filter((c) => c.severity === "warning") : [];
  const nothing = built?.ok ? !built.rows.sql.length : true;

  return (
    // Less above than below: the first section header's own row (32 px)
    // already sets its name off the divider.
    <Box sx={{ px: PX, pt: "4px", pb: "12px", borderTop: 1, borderColor: "divider", flexShrink: 0 }}>
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
      {/* The cost set off from what follows, warnings or the buttons, by a
          line across the panel, as the bar is from the panel above it. */}
      <Box sx={{ mx: -PX, mt: "12px", borderTop: 1, borderColor: "divider" }} />
      {warnings.map((w) => (
        <Typography key={w.code} variant="caption" display="block" sx={{ mt: "8px", color: "warning.dark" }}>
          {checkWords(w, t)}
        </Typography>
      ))}
      {/* A refusal about a form field is said on the field, not again here. */}
      {refused && !refused.field && (
        <Typography variant="caption" display="block" color="error" sx={{ mt: "8px" }}>
          {checkWords(refused, t)}
        </Typography>
      )}
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
