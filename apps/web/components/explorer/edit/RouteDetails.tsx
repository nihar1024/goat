/**
 * A line's Properties tab, for an editor, as a stop's (board 26): its own
 * GTFS fields (routes.txt) in the Explorer's settings rows, each change a
 * draft the Apply bar applies; a problem said on its field once it was
 * touched. Its ID shown, not edited: trips and other tables name it. At the
 * foot, at the right, its delete; what that takes with it is said once it
 * is pressed (the delete card, 1.5).
 */
import { Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import {
  type Continuous,
  type RouteField,
  type RouteValues,
  routeFieldProblems,
  sameRouteValues,
} from "@/lib/explorer/edit/ops/routes";
import { modeOf } from "@/lib/explorer/modes";
import { setEditDraft } from "@/lib/store/explorer/slice";

import { useDraftEditShown } from "@/hooks/explorer/useDraftEdit";
import { useAgencies, useRouteRecord } from "@/hooks/explorer/useExplorerData";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import { useExplorer } from "@/components/explorer/ExplorerContext";
import { PX } from "@/components/explorer/SectionHeader";
import { DetailsSection, FIELD_SX, OPTION_SX, POPUP_SX, Row } from "@/components/explorer/edit/StopDetails";
import { modeIcon } from "@/components/explorer/modeIcon";

/** The basic route types, in the order riders meet them most. */
const ROUTE_TYPES = [3, 11, 0, 1, 2, 12, 4, 5, 6, 7];
/** Continuous stopping as GTFS has it; none first (most lines). */
const CONTINUOUS: Continuous[] = [null, 0, 2, 3];

export function RouteDetails({ route_idx }: { route_idx: number }) {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const { db } = useExplorer();
  const query = useRouteRecord(db, route_idx);
  const agencies = useAgencies(db).data ?? [];
  const draft = useAppSelector((s) => s.explorer.edit.draft);
  const edit = useDraftEditShown();
  const deleting = draft?.kind === "line-delete" && draft.route_idx === route_idx;
  // A problem is said on its field once it was left or changed.
  const [touched, setTouched] = useState<Set<RouteField>>(() => new Set());
  const record = query.data;
  if (query.error)
    return (
      <Typography variant="body2" color="error" sx={{ mt: 2 }}>
        {query.error}
      </Typography>
    );
  if (!record) return null;

  const { route_idx: _i, route_id, ...saved } = record;
  const values = draft?.kind === "route-details" && draft.route_idx === route_idx ? draft.values : saved;
  // Back where it was: nothing to apply.
  const set = (f: RouteField, next: Partial<RouteValues>) => {
    setTouched((s) => (s.has(f) ? s : new Set(s).add(f)));
    const v = { ...values, ...next };
    dispatch(
      setEditDraft(sameRouteValues(v, saved) ? null : { kind: "route-details", route_idx, values: v })
    );
  };
  const problems = routeFieldProblems(values);
  const refused =
    edit?.draft.kind === "route-details" && edit.built && !edit.built.ok ? edit.built.refused : null;
  const error = (f: RouteField) => {
    const code = touched.has(f)
      ? (problems[f] ?? (refused?.field === f ? refused.code : undefined))
      : undefined;
    return code ? t(`explorer_field_${code}`) : undefined;
  };
  const text = (f: "short_name" | "long_name" | "description" | "url" | "sort_order", label: string) => (
    <Row label={label}>
      <TextField
        size="small"
        fullWidth
        value={values[f]}
        error={!!error(f)}
        helperText={error(f)}
        onBlur={() => setTouched((s) => new Set(s).add(f))}
        onChange={(e) => set(f, { [f]: e.target.value })}
        inputProps={{ "aria-label": label, ...(f === "sort_order" ? { inputMode: "numeric" } : {}) }}
        sx={FIELD_SX}
      />
    </Row>
  );
  const color = (f: "color" | "text_color", label: string) => {
    const hex = values[f].trim().replace(/^#/, "");
    return (
      <Row label={label}>
        <TextField
          size="small"
          fullWidth
          value={values[f]}
          placeholder="RRGGBB"
          error={!!error(f)}
          helperText={error(f)}
          onBlur={() => setTouched((s) => new Set(s).add(f))}
          onChange={(e) => set(f, { [f]: e.target.value })}
          inputProps={{ "aria-label": label }}
          InputProps={{
            // The colour as it is typed, once it is one.
            startAdornment: (
              <Box
                aria-hidden
                sx={{
                  ml: 1,
                  width: 14,
                  height: 14,
                  flexShrink: 0,
                  borderRadius: "3px",
                  border: 1,
                  borderColor: "divider",
                  bgcolor: /^[0-9A-Fa-f]{6}$/.test(hex) ? `#${hex}` : "transparent",
                }}
              />
            ),
          }}
          sx={FIELD_SX}
        />
      </Row>
    );
  };
  const select = <V extends string | number>(
    label: string,
    value: V,
    options: { value: V; label: string; icon?: ICON_NAME }[],
    onChange: (v: string) => void
  ) => (
    <Row label={label}>
      <TextField
        select
        size="small"
        fullWidth
        value={value}
        onChange={(e) => onChange(e.target.value)}
        SelectProps={{
          SelectDisplayProps: { "aria-label": label },
          MenuProps: { PaperProps: { sx: POPUP_SX } },
        }}
        sx={FIELD_SX}>
        {options.map((o) => (
          <MenuItem key={String(o.value)} value={o.value} sx={OPTION_SX}>
            <Stack direction="row" alignItems="center" spacing="8px" sx={{ minWidth: 0 }}>
              {o.icon && <Icon iconName={o.icon} style={{ fontSize: 12 }} htmlColor="inherit" />}
              <Typography noWrap sx={{ fontSize: "0.8125rem" }}>
                {o.label}
              </Typography>
            </Stack>
          </MenuItem>
        ))}
      </TextField>
    </Row>
  );
  const typeLabel = (k: number) =>
    k in BASIC_LABELS ? t(`explorer_mode_${modeOf(k)}`) : `${t(`explorer_mode_${modeOf(k)}`)} (${k})`;
  const continuousOptions = CONTINUOUS.map((c) => ({
    value: c === null ? "none" : String(c),
    label: t(`explorer_continuous_${c === null ? "none" : c}`),
  }));
  const continuousOf = (v: string): Continuous => (v === "none" ? null : (Number(v) as Continuous));

  return (
    <Stack sx={{ minHeight: "100%", pb: 2, mx: -2.5 }}>
      <DetailsSection first ruled icon={ICON_NAME.EDIT} label={t("explorer_stop_tab_properties")}>
        <Stack spacing="16px" sx={{ px: PX }}>
          <Row label={t("explorer_line_field_id")}>
            <Typography sx={{ fontSize: "0.8125rem", lineHeight: "32px", wordBreak: "break-all" }}>
              {route_id}
            </Typography>
          </Row>
          {text("short_name", t("explorer_line_field_short_name"))}
          {text("long_name", t("explorer_line_field_long_name"))}
          {text("description", t("explorer_line_field_description"))}
          {select(
            t("explorer_line_field_mode"),
            values.route_type,
            [...ROUTE_TYPES, ...(ROUTE_TYPES.includes(values.route_type) ? [] : [values.route_type])].map(
              (k) => ({
                value: k,
                label: typeLabel(k),
                icon: modeIcon(modeOf(k)),
              })
            ),
            (v) => set("route_type", { route_type: Number(v) })
          )}
          {/* An agency to choose only where the feed has more than one. */}
          {agencies.length > 1 &&
            select(
              t("explorer_line_field_agency"),
              values.agency_idx,
              agencies.map((a) => ({ value: a.agency_idx, label: a.name ?? String(a.agency_idx) })),
              (v) => set("agency_idx", { agency_idx: Number(v) })
            )}
          {color("color", t("explorer_line_field_color"))}
          {color("text_color", t("explorer_line_field_text_color"))}
          {text("url", t("explorer_line_field_url"))}
          {text("sort_order", t("explorer_line_field_sort_order"))}
          {select(
            t("explorer_line_field_continuous_pickup"),
            values.continuous_pickup === null ? "none" : String(values.continuous_pickup),
            continuousOptions,
            (v) => set("continuous_pickup", { continuous_pickup: continuousOf(v) })
          )}
          {select(
            t("explorer_line_field_continuous_drop_off"),
            values.continuous_drop_off === null ? "none" : String(values.continuous_drop_off),
            continuousOptions,
            (v) => set("continuous_drop_off", { continuous_drop_off: continuousOf(v) })
          )}
        </Stack>
      </DetailsSection>
      {!deleting && (
        <Stack direction="row" justifyContent="flex-end" sx={{ px: PX, mt: "auto", pt: 2 }}>
          <Button
            size="small"
            variant="outlined"
            color="error"
            onClick={() => dispatch(setEditDraft({ kind: "line-delete", route_idx, stops: false }))}
            startIcon={<Icon iconName={ICON_NAME.TRASH} style={{ fontSize: 12 }} htmlColor="inherit" />}
            sx={{ flexShrink: 0, borderRadius: "16px", px: 1.5, fontWeight: 700, textTransform: "none" }}>
            {t("explorer_delete_line")}
          </Button>
        </Stack>
      )}
    </Stack>
  );
}

/** The basic types, named by their mode alone. */
const BASIC_LABELS: Record<number, true> = Object.fromEntries(ROUTE_TYPES.map((k) => [k, true]));
