/**
 * Under the edit bar while a tool other than Select is on (board 18): the
 * tool, what a click does with it, and the way back.
 */
import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

import { useAppSelector } from "@/hooks/store/ContextHooks";

export function ToolHint() {
  const { t } = useTranslation("common");
  const tool = useAppSelector((s) => s.explorer.edit.tool);
  if (tool !== "stop") return null;
  return (
    <Box
      role="status"
      sx={{
        mt: "8px",
        width: "fit-content",
        display: "flex",
        alignItems: "center",
        columnGap: "8px",
        height: 28,
        px: "12px",
        borderRadius: "14px",
        // As the bar's count once something changed: dark, on the map.
        bgcolor: "text.primary",
        color: "background.paper",
        boxShadow: "rgba(0, 0, 0, 0.2) 0px 0px 10px",
        pointerEvents: "none",
      }}>
      <Typography color="inherit" sx={{ fontSize: 12, fontWeight: 700 }}>
        {t(`explorer_tool_${tool}`)}
      </Typography>
      <Typography color="inherit" sx={{ fontSize: 12, opacity: 0.85 }}>
        {t(`explorer_tool_${tool}_hint`)}
      </Typography>
    </Box>
  );
}
