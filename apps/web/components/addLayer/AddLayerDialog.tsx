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
  Tooltip,
  Typography,
  useTheme,
} from "@mui/material";
import type { ReactNode } from "react";
import { useState } from "react";
import { useMap } from "react-map-gl/maplibre";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { FlowController } from "@/hooks/addLayer/flow";

import { useCatalogFlow } from "@/hooks/addLayer/useCatalogFlow";
import { useCreateFlow } from "@/hooks/addLayer/useCreateFlow";
import { useUploadFlow } from "@/hooks/addLayer/useUploadFlow";

import CatalogBody from "@/components/addLayer/CatalogBody";
import CreateBody from "@/components/addLayer/CreateBody";
import UploadBody from "@/components/addLayer/UploadBody";
import { ADD_LAYER_SOURCES, type AddLayerSourceId } from "@/components/addLayer/sources";

/**
 * The chrome one source is shown in: a title, the body, and the flow's own control.
 *
 * A frame per source rather than one dialog holding all of them behind a tab bar. The
 * sources are not peers — uploading a file is a short form, browsing the catalog is a
 * search over thousands of collections — and each is sized for its own job here, which is
 * why nothing in this file animates a width or hides a body while the frame moves.
 *
 * It owns none of the rules: the flow publishes an `action` and the footer draws it.
 */
const AddLayerFrame = ({
  sourceId,
  controller,
  onClose,
  children,
}: {
  sourceId: AddLayerSourceId;
  controller: FlowController;
  onClose: () => void;
  children: ReactNode;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const source = ADD_LAYER_SOURCES.find((entry) => entry.id === sourceId);

  const close = () => {
    controller.reset();
    onClose();
  };

  return (
    <Dialog
      open
      onClose={close}
      maxWidth={false}
      // Set outright rather than capped, because each source has a width of its own and
      // MUI's paper rules would otherwise win.
      PaperProps={{ sx: { width: source?.width ?? 860, maxWidth: "94vw" } }}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={3}
        sx={{ borderBottom: `1px solid ${theme.palette.divider}`, pl: 6, pr: 3, py: 3 }}>
        {source && (
          <Icon
            iconName={source.icon}
            style={{ fontSize: 15 }}
            htmlColor={theme.palette.text.secondary}
          />
        )}
        <Typography variant="body1" fontWeight="bold" sx={{ flex: 1, minWidth: 0 }}>
          {t(source?.labelKey ?? "add_layer")}
        </Typography>
        <IconButton size="small" onClick={close} aria-label={t("close")}>
          <Icon iconName={ICON_NAME.XCLOSE} style={{ fontSize: 15 }} />
        </IconButton>
      </Stack>

      {/* A browsing source lays out its own edges — a filter rail has to reach the frame —
          so the dialog does not pad it and leave it to undo that. Forms keep their padding. */}
      <DialogContent sx={source?.wide ? { p: 0 } : { pt: 5 }}>{children}</DialogContent>

      <DialogActions
        disableSpacing
        // The doubled `&` is load-bearing: the theme zeroes a dialog footer's top padding
        // through `.MuiDialogContent-root + .MuiDialogActions-root`, which ties with a
        // normal `sx` selector on specificity and wins on order, so the buttons sat against
        // the rule. Three classes settle it.
        sx={{
          "&&.MuiDialogActions-root": {
            borderTop: `1px solid ${theme.palette.divider}`,
            py: 4,
            px: 6,
          },
          justifyContent: "flex-end",
          gap: 2,
        }}>
        <Button variant="text" onClick={close}>
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <Tooltip title={controller.action.disabled ? (controller.action.reason ?? "") : ""}>
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
      </DialogActions>
    </Dialog>
  );
};

/**
 * One wrapper per source, so only the flow being used is mounted.
 *
 * Hooks cannot be called conditionally, so a single component holding all three would run
 * all three: opening the upload dialog would start the catalog flow's queries as well.
 * Split, each dialog costs only what it is for.
 */
const UploadDialog = ({
  projectId,
  defaultFolderId,
  initialFile,
  autoOpenSetup,
  onClose,
}: {
  projectId?: string;
  defaultFolderId?: string;
  initialFile?: File;
  autoOpenSetup?: boolean;
  onClose: () => void;
}) => {
  const controller = useUploadFlow({ projectId, defaultFolderId, initialFile, onDone: onClose });
  return (
    <AddLayerFrame sourceId="upload" controller={controller} onClose={onClose}>
      <UploadBody controller={controller} autoOpenSetup={autoOpenSetup} />
    </AddLayerFrame>
  );
};

const CreateDialog = ({ projectId, onClose }: { projectId?: string; onClose: () => void }) => {
  const controller = useCreateFlow({ projectId, onDone: onClose });
  return (
    <AddLayerFrame sourceId="create" controller={controller} onClose={onClose}>
      <CreateBody controller={controller} />
    </AddLayerFrame>
  );
};

const CatalogDialog = ({ projectId, onClose }: { projectId?: string; onClose: () => void }) => {
  const { map } = useMap();
  /**
   * Read once, when the dialog opens: the map cannot move behind a modal, and
   * a value that changed would refetch the whole list. Absent on the dashboard,
   * where there is no map — then nothing is boosted.
   */
  const [viewport] = useState<[number, number, number, number] | undefined>(() => {
    const bounds = map?.getBounds();
    return bounds
      ? [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]
      : undefined;
  });
  const controller = useCatalogFlow({ projectId, onDone: onClose, viewport });
  return (
    <AddLayerFrame sourceId="catalog" controller={controller} onClose={onClose}>
      <CatalogBody controller={controller} />
    </AddLayerFrame>
  );
};

/**
 * A layer from one source, in a dialog of its own.
 *
 * Nothing is mounted until a source is asked for, so a host may render this permanently.
 * Sources that still live in their own dialog are not handled here — the menu opens those
 * directly, since there is no reason to route them through this frame.
 */
const AddLayerDialog = ({
  source,
  projectId,
  defaultFolderId,
  initialFile,
  autoOpenSetup,
  onClose,
}: {
  /** Which source to show; `null` shows nothing. */
  source: AddLayerSourceId | null;
  projectId?: string;
  defaultFolderId?: string;
  /** A file the host already holds, e.g. one dropped on the map. */
  initialFile?: File;
  /** Opens the file's own settings as soon as they can be shown. */
  autoOpenSetup?: boolean;
  onClose: () => void;
}) => {
  if (source === "upload")
    return (
      <UploadDialog
        projectId={projectId}
        defaultFolderId={defaultFolderId}
        initialFile={initialFile}
        autoOpenSetup={autoOpenSetup}
        onClose={onClose}
      />
    );
  if (source === "create") return <CreateDialog projectId={projectId} onClose={onClose} />;
  if (source === "catalog") return <CatalogDialog projectId={projectId} onClose={onClose} />;
  return null;
};

export default AddLayerDialog;
