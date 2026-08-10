import { Box, Divider, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

/**
 * Labelled rule that separates beta tools from the stable ones at the bottom of
 * a palette category. Shared by the map toolbox and the workflow node palette so
 * both read the same.
 */
export default function BetaSectionDivider() {
  const { t } = useTranslation("common");
  const theme = useTheme();

  return (
    <Box sx={{ mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
      <Divider sx={{ width: 8, flexShrink: 0 }} />
      <Box
        sx={{
          flexShrink: 0,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          height: 14,
          minWidth: 28,
          px: 0.625,
          borderRadius: "4px",
          // Muted, inverted pill that adapts to the theme (text.secondary is a
          // mode-aware foreground; paper is the surface behind it) instead of
          // hardcoded hex that reads as a glaring light-grey chip in dark mode.
          bgcolor: theme.palette.text.secondary,
          color: theme.palette.background.paper,
          fontSize: "8px",
          fontWeight: 700,
          fontFamily: "Arial, sans-serif",
          lineHeight: 1,
          letterSpacing: "0.02em",
          textTransform: "none",
        }}>
        {t("beta")}
      </Box>
      <Divider sx={{ flexGrow: 1 }} />
    </Box>
  );
}
