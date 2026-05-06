import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import type { PopupPlacement, PopupSize, PopupType } from "@/lib/validations/widget";

export type PopupTypeValue = PopupType;
export type PopupPlacementValue = PopupPlacement;
export type PopupSizeValue = PopupSize;

interface PopupSettingsControlsProps {
  popupType: PopupType;
  placement: PopupPlacement;
  size: PopupSize;
  onPopupTypeChange: (value: PopupType) => void;
  onPlacementChange: (value: PopupPlacement) => void;
  onSizeChange: (value: PopupSize) => void;
}

/**
 * Shared popup-display controls (type / placement / size) used by every
 * popup editor (InfoChip, Links, Project info). Keeps the dialogs visually
 * identical and makes adding/changing options a single edit.
 */
const PopupSettingsControls = ({
  popupType,
  placement,
  size,
  onPopupTypeChange,
  onPlacementChange,
  onSizeChange,
}: PopupSettingsControlsProps) => {
  const { t } = useTranslation("common");
  const showPlacement = popupType !== "dialog";

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ mb: 0.5, display: "block" }}>
          {t("popup_type")}
        </Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={popupType}
          onChange={(_, v) => {
            if (v) onPopupTypeChange(v as PopupTypeValue);
          }}
          sx={{ width: "100%" }}>
          <ToggleButton value="tooltip" sx={{ flex: 1, fontSize: 12, py: 0.75, textTransform: "none" }}>
            {t("tooltip")}
          </ToggleButton>
          <ToggleButton value="popover" sx={{ flex: 1, fontSize: 12, py: 0.75, textTransform: "none" }}>
            {t("popup")}
          </ToggleButton>
          <ToggleButton value="dialog" sx={{ flex: 1, fontSize: 12, py: 0.75, textTransform: "none" }}>
            {t("popup_dialog")}
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {showPlacement && (
        <Box>
          <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ mb: 0.5, display: "block" }}>
            {t("popup_placement")}
          </Typography>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={placement}
            onChange={(_, v) => {
              if (v) onPlacementChange(v as PopupPlacementValue);
            }}
            sx={{ width: "100%" }}>
            <ToggleButton value="auto" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
              {t("placement_auto")}
            </ToggleButton>
            <ToggleButton value="top" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
              {t("placement_top")}
            </ToggleButton>
            <ToggleButton value="bottom" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
              {t("placement_bottom")}
            </ToggleButton>
            <ToggleButton value="left" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
              {t("placement_left")}
            </ToggleButton>
            <ToggleButton value="right" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
              {t("placement_right")}
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
      )}

      <Box>
        <Typography variant="caption" color="text.secondary" fontWeight={600} sx={{ mb: 0.5, display: "block" }}>
          {t("popup_size")}
        </Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={size}
          onChange={(_, v) => {
            if (v) onSizeChange(v as PopupSizeValue);
          }}
          sx={{ width: "100%" }}>
          <ToggleButton value="sm" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
            {t("size_small")}
          </ToggleButton>
          <ToggleButton value="md" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
            {t("size_medium")}
          </ToggleButton>
          <ToggleButton value="lg" sx={{ flex: 1, fontSize: 12, py: 0.5, textTransform: "none" }}>
            {t("size_large")}
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>
    </Stack>
  );
};

export default PopupSettingsControls;
