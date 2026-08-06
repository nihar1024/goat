"use client";

import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import { Trans, useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

/**
 * The panel a file's own settings open in, on top of whatever opened it.
 *
 * Deliberately empty of subject knowledge: it owns the frame, the title, the close and
 * the footer, and takes the settings themselves as children. A workbook's header row is
 * the only thing that needs it today; a shapefile's encoding, a projection, a column
 * mapping would each be another `children` and no change here.
 *
 * Its own dialog rather than a section of the upload screen, because these settings are
 * a detour that most uploads never take, and a preview table needs more width than the
 * screen that sent you here.
 */
const LayerSetupDialog = ({
  open,
  fileName,
  onClose,
  onSave,
  children,
}: {
  open: boolean;
  /** The file being set up, for the accessible name of the dialog. */
  fileName: string;
  onClose: () => void;
  onSave: () => void;
  children: React.ReactNode;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      aria-label={fileName}
      maxWidth={false}
      // Wider than the screen that opened it: a preview can run to dozens of columns, and
      // this is the one place they are meant to be read.
      PaperProps={{ sx: { width: "min(1100px, 94vw)" } }}>
      {/* `DialogTitle` with plain text, as every other dialog here does: the theme styles
          it (padding included), so a custom `variant` and weight would make this the one
          title that does not match. */}
      <DialogTitle>
        <Stack direction="row" alignItems="flex-start" spacing={3}>
          <Stack spacing={1} sx={{ flex: 1, minWidth: 0 }}>
            {t("upload_set_up_columns")}
            {/* The file is named here rather than in the title: this is a sentence about
                it, and body text wraps where a heading would be pushed out of the frame by
                an export named after the query that produced it. */}
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ overflowWrap: "anywhere" }}>
              <Trans
                i18nKey="upload_set_up_intro"
                t={t}
                values={{ file: fileName }}
                components={{ file: <Box component="span" sx={{ fontWeight: 700 }} /> }}
              />
            </Typography>
          </Stack>
          <IconButton size="small" onClick={onClose} aria-label={t("close")}>
            <Icon iconName={ICON_NAME.XCLOSE} style={{ fontSize: 15 }} />
          </IconButton>
        </Stack>
      </DialogTitle>

      <DialogContent sx={{ pt: 3 }}>{children}</DialogContent>

      <DialogActions
        disableSpacing
        sx={{
          "&&.MuiDialogActions-root": {
            borderTop: `1px solid ${theme.palette.divider}`,
            py: 4,
            px: 6,
          },
          justifyContent: "flex-end",
          gap: 2,
        }}>
        <Button variant="text" onClick={onClose}>
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <Button variant="contained" color="primary" onClick={onSave}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("confirm")}
          </Typography>
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default LayerSetupDialog;
