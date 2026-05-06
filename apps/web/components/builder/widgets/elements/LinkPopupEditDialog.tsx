import CloseIcon from "@mui/icons-material/Close";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
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
} from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import type { PopupPlacement, PopupSize, PopupType } from "@/lib/validations/widget";

import MarkdownContentEditor from "@/components/builder/widgets/common/MarkdownContentEditor";
import PopupSettingsControls from "@/components/builder/widgets/common/PopupSettingsControls";

export interface LinkPopupValues {
  popup_content?: string;
  popup_type?: PopupType;
  popup_placement?: PopupPlacement;
  popup_size?: PopupSize;
}

interface LinkPopupEditDialogProps {
  open: boolean;
  onClose: () => void;
  onSave: (values: LinkPopupValues) => void;
  initial: LinkPopupValues;
  /** Used as the dialog header context, e.g. the link's label. */
  contextLabel?: string;
}

/**
 * Per-link popup edit dialog. Visually identical to InfoChipEditDialog —
 * shares the same dialog frame, controls, and content editor.
 */
const LinkPopupEditDialog = ({
  open,
  onClose,
  onSave,
  initial,
  contextLabel: _contextLabel,
}: LinkPopupEditDialogProps) => {
  const { t } = useTranslation("common");
  const [popupType, setPopupType] = useState<PopupType>("popover");
  const [placement, setPlacement] = useState<PopupPlacement>("auto");
  const [size, setSize] = useState<PopupSize>("md");
  const [content, setContent] = useState("");

  useEffect(() => {
    if (!open) return;
    setPopupType(initial.popup_type ?? "popover");
    setPlacement(initial.popup_placement ?? "auto");
    setSize(initial.popup_size ?? "md");
    setContent(initial.popup_content ?? "");
    // Snapshot when the dialog opens; ignore prop churn while editing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = () => {
    onSave({
      popup_type: popupType,
      popup_placement: placement,
      popup_size: size,
      popup_content: content,
    });
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pr: 6, display: "flex", alignItems: "center", gap: 1 }}>
        <InfoOutlinedIcon sx={{ fontSize: 20, color: "primary.main", opacity: 0.85 }} />
        <Typography variant="h6" sx={{ flex: 1 }}>
          {t("edit_popup_content")}
        </Typography>
        <IconButton size="small" onClick={handleClose} sx={{ position: "absolute", right: 12, top: 12 }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Stack spacing={2}>
          <PopupSettingsControls
            popupType={popupType}
            placement={placement}
            size={size}
            onPopupTypeChange={setPopupType}
            onPlacementChange={setPlacement}
            onSizeChange={setSize}
          />

          <Box>
            <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ mb: 0.5, display: "block" }}>
              {t("info_text", { defaultValue: "Info text" })}
            </Typography>
            <MarkdownContentEditor
              value={content}
              onChange={setContent}
              plainText={popupType === "tooltip"}
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={handleClose} variant="contained" size="small">
          {t("done", { defaultValue: "Done" })}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default LinkPopupEditDialog;
