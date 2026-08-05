"use client";

import { Box, Button, Stack, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import { Icon } from "@p4b/ui/components/Icon";
import type { ICON_NAME } from "@p4b/ui/components/Icon";

/**
 * A tab for a source that has no flow yet: it explains itself and opens the dialog
 * that still owns it.
 *
 * Needed because the modal replaces a menu — without it, every source we have not
 * rebuilt would simply vanish from the product. Each panel is deleted with the tab
 * it stands in for.
 */
const HandoffPanel = ({
  labelKey,
  icon,
  onOpen,
}: {
  labelKey: string;
  icon: ICON_NAME;
  onOpen: () => void;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  return (
    <Stack alignItems="center" justifyContent="center" spacing={4} sx={{ py: 14, px: 6 }}>
      <Box
        sx={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: theme.palette.action.hover,
        }}>
        <Icon iconName={icon} style={{ fontSize: 22 }} htmlColor={theme.palette.text.secondary} />
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 380, textAlign: "center" }}>
        {t("add_layer_handoff_note", { source: t(labelKey) })}
      </Typography>
      <Button variant="contained" onClick={onOpen}>
        {t("add_layer_handoff_open", { source: t(labelKey) })}
      </Button>
    </Stack>
  );
};

export default HandoffPanel;
