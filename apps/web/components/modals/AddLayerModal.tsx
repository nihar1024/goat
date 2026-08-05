"use client";

import LoadingButton from "@mui/lab/LoadingButton";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  IconButton,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Tab,
  Tabs,
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { AddLayerSourceType } from "@/types/common";

import { useCatalogFlow } from "@/hooks/addLayer/useCatalogFlow";
import { useCreateFlow } from "@/hooks/addLayer/useCreateFlow";
import { useUploadFlow } from "@/hooks/addLayer/useUploadFlow";

import {
  ADD_LAYER_WIDE_WIDTH,
  type AddLayerSourceId,
  sourcesFor,
} from "@/components/addLayer/sources";
import HandoffPanel from "@/components/addLayer/HandoffPanel";
import CatalogBody from "@/components/addLayer/CatalogBody";
import CreateBody from "@/components/addLayer/CreateBody";
import UploadBody from "@/components/addLayer/UploadBody";

/**
 * Every way a layer enters a project or a dataset list, in one dialog.
 *
 * This is a **host**: it owns the frame, the tab bar, how steps are drawn, the
 * footer and the width. It owns none of the rules — each flow publishes an `action`
 * (label, disabled, what to run) and the footer draws it. A side panel or a page
 * can host the same flows without any of this file.
 *
 * Replaces the button-plus-menu that opened five separate dialogs.
 */
/** How long the paper takes to change width, and the value the CSS below is built from. */
const WIDTH_MS = 260;

/**
 * How long the body waits before fading back in.
 *
 * Short of the full width transition on purpose: it is eased, so its last frames cover
 * a handful of the ~500px travelled — far less than a column of cards, and nothing the
 * eye reads as a reveal. Ending the wait there means the tab arrives as the frame
 * settles rather than after it, which is what keeps the gap from wanting a spinner.
 */
const WIDTH_TRANSITION_MS = 200;

const AddLayerModal = ({
  open,
  onClose,
  projectId,
  defaultFolderId,
  sources: allowed,
  onOpenLegacy,
}: {
  open: boolean;
  onClose: () => void;
  projectId?: string;
  defaultFolderId?: string;
  /** Restricts the tabs; by default every source the host supports is offered. */
  sources?: AddLayerSourceId[];
  /**
   * Opens the dialog a source still lives in — see `HandoffPanel`. Without it the
   * not-yet-rebuilt sources are left out entirely, which is what a host wanting
   * only the upload flow should do.
   */
  onOpenLegacy?: (source: AddLayerSourceType) => void;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  const sources = useMemo(() => {
    const supported = sourcesFor({ hasProject: !!projectId }).filter(
      (entry) => entry.handoff === undefined || !!onOpenLegacy
    );
    return allowed ? supported.filter((entry) => allowed.includes(entry.id)) : supported;
  }, [projectId, onOpenLegacy, allowed]);
  const [active, setActive] = useState<AddLayerSourceId>(sources[0].id);
  const source = sources.find((entry) => entry.id === active) ?? sources[0];

  /**
   * True while the paper is animating between the two widths.
   *
   * The content stays put and stays laid out — it is only hidden. A dialog grows from
   * its centre, so a body anchored to its left edge is *uncovered* as the frame moves
   * outwards: the third column of cards appears halfway through, which reads as the
   * modal sliding off its own contents. Hidden until the frame has settled, the tab
   * simply appears at the size it belongs at.
   *
   * Decided during render, not in an effect: an effect runs *after* the browser has
   * painted, so the new body appeared at full opacity for a frame, vanished, and came
   * back. A render-phase update re-renders before anything reaches the screen.
   *
   * Only when the width actually changes: switching between two tabs of the same width
   * has nothing to wait for.
   */
  const wide = !!source.wide;
  const [resizing, setResizing] = useState(false);
  const [paintedWide, setPaintedWide] = useState(wide);
  if (paintedWide !== wide) {
    setPaintedWide(wide);
    setResizing(true);
  }
  useEffect(() => {
    if (!resizing) return;
    const done = setTimeout(() => setResizing(false), WIDTH_TRANSITION_MS);
    return () => clearTimeout(done);
  }, [resizing]);

  // Called unconditionally, as hooks must be. Later flows join it here; each one
  // that fetches should take the active tab into account rather than idling on a
  // request nobody is looking at.
  const upload = useUploadFlow({ projectId, defaultFolderId, onDone: onClose });
  const create = useCreateFlow({ projectId, onDone: onClose });
  const catalog = useCatalogFlow({ projectId, onDone: onClose });
  const flows = { upload, create, catalog } as const;
  const controller =
    source.id === "upload"
      ? upload
      : source.id === "create"
        ? create
        : source.id === "catalog"
          ? catalog
          : null;

  const close = () => {
    flows.upload.reset();
    flows.create.reset();
    flows.catalog.reset();
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      maxWidth={false}
      // A browsing tab carries a filter rail beside a list of cards, so it gets most
      // of a desktop; a form tab stays a form. `width` is set outright rather than
      // capped, because that is the property being animated — and `!important`
      // because MUI's own paper width rules would otherwise win.
      PaperProps={{
        sx: {
          width: wide ? ADD_LAYER_WIDE_WIDTH : 860,
          maxWidth: "94vw",
          transition: `width ${WIDTH_MS}ms var(--ease-in-out) !important`,
        },
      }}>
      <Stack
        direction="row"
        alignItems="center"
        // Off the modal's edges, and off its top: tabs hard against the frame read
        // as cramped, and the rule under them needs room to be a rule.
        sx={{ borderBottom: `1px solid ${theme.palette.divider}`, pl: 4, pr: 3 }}>
        <Tabs
          value={active}
          onChange={(_, value) => setActive(value as AddLayerSourceId)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ flex: 1, minHeight: 44 }}>
          {sources.map((entry) => (
            <Tab
              key={entry.id}
              value={entry.id}
              // The source's own icon, `start`-positioned so the tab is a row
              // rather than MUI's default stack — which would double its height.
              icon={<Icon iconName={entry.icon} style={{ fontSize: 13 }} />}
              iconPosition="start"
              label={t(entry.labelKey)}
              // The bar's breathing room lives in the tab, not around it: as the
              // row's padding it left every hover and focus ring floating below a
              // gap, which read as a chip pasted onto the header.
              sx={{
                textTransform: "none",
                fontSize: 13.5,
                fontWeight: 600,
                minHeight: 52,
                minWidth: 0,
                px: 2.5,
                pt: 1.75,
                pb: 0.75,
                gap: 1.5,
              }}
            />
          ))}
        </Tabs>
        <IconButton size="small" onClick={close} aria-label={t("close")}>
          <Icon iconName={ICON_NAME.XCLOSE} style={{ fontSize: 15 }} />
        </IconButton>
      </Stack>

      {/* Browsing tabs lay out their own edges — a filter rail has to reach the
          frame — so the dialog does not pad them and then leave the tab to undo it.
          Form tabs keep the padding they want. */}
      <DialogContent
        sx={
          source.wide
            ? // No horizontal scrollbar while the paper is still narrower than the
              // body it is growing to hold.
              { p: 0, overflowX: "hidden" }
            : { pt: 5 }
        }>
        {controller && controller.steps.length > 1 && (
          <Box sx={{ width: "100%", mb: 6 }}>
            <Stepper activeStep={controller.step} alternativeLabel>
              {controller.steps.map((label) => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>
          </Box>
        )}

        <Box
          data-testid="add-layer-body"
          sx={{
            opacity: resizing ? 0 : 1,
            // Gone at once, back gradually: fading *out* over 160ms leaves the body on
            // screen for the first part of the resize, which is the very moment the
            // frame is uncovering it.
            transition: resizing
              ? "none"
              : theme.transitions.create("opacity", { duration: 120 }),
          }}>
          {source.id === "upload" && <UploadBody controller={upload} />}
          {source.id === "create" && <CreateBody controller={create} />}
          {source.id === "catalog" && <CatalogBody controller={catalog} />}
          {source.handoff !== undefined && (
            <HandoffPanel
              labelKey={source.labelKey}
              icon={source.icon}
              onOpen={() => {
                const legacy = source.handoff as AddLayerSourceType;
                close();
                onOpenLegacy?.(legacy);
              }}
            />
          )}
        </Box>
      </DialogContent>

      {controller && (
        <DialogActions
          disableSpacing
          // A rule, matching the one under the tabs: without it the footer read as
          // the last row of whatever the tab was showing rather than as the dialog's
          // own controls, and the buttons need room to sit off it.
          //
          // The doubled `&` is load-bearing: the theme zeroes a dialog footer's top
          // padding through `.MuiDialogContent-root + .MuiDialogActions-root`, which
          // ties with a normal `sx` selector on specificity and wins on order, so the
          // buttons sat against the rule. Three classes settle it.
          sx={{
            "&&.MuiDialogActions-root": {
              borderTop: `1px solid ${theme.palette.divider}`,
              py: 4,
              px: 6,
            },
            justifyContent: "space-between",
          }}>
          <Box>
            {controller.step > 0 && (
              <Button variant="text" onClick={() => controller.goTo(controller.step - 1)}>
                <Typography variant="body2" fontWeight="bold">
                  {t("back")}
                </Typography>
              </Button>
            )}
          </Box>
          <Stack direction="row" spacing={2}>
            <Button variant="text" onClick={close}>
              <Typography variant="body2" fontWeight="bold">
                {t("cancel")}
              </Typography>
            </Button>
            {/* One control for every flow and every step: the label, the enabled
                state and the work all come from the flow's `action`. */}
            <Tooltip title={controller.action.disabled ? controller.action.reason ?? "" : ""}>
              <Box component="span" sx={{ display: "inline-flex" }}>
                <LoadingButton
                  variant="contained"
                  color="primary"
                  disabled={controller.action.disabled}
                  loading={controller.isBusy}
                  onClick={() => void controller.action.run()}>
                  <Typography variant="body2" fontWeight="bold" color="inherit">
                    {controller.action.label}
                  </Typography>
                </LoadingButton>
              </Box>
            </Tooltip>
          </Stack>
        </DialogActions>
      )}
    </Dialog>
  );
};

export default AddLayerModal;
