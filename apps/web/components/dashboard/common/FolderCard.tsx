import { Box, IconButton, Paper, Stack, Tooltip, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { Folder } from "@/lib/validations/folder";

import type { PopperMenuItem } from "@/components/common/PopperMenu";
import MoreMenu from "@/components/common/PopperMenu";

interface FolderCardProps {
  folder: Folder;
  selected?: boolean;
  enableActions?: boolean;
  showRoleChip?: boolean;
  fullWidth?: boolean;
  onClick: (folder: Folder) => void;
  onMenuSelect?: (item: PopperMenuItem, folder: Folder) => void;
}

export default function FolderCard({ folder, selected, enableActions, showRoleChip, fullWidth, onClick, onMenuSelect }: FolderCardProps) {
  const isShared = !showRoleChip && folder.is_owned && (folder.shared_with_ids?.length ?? 0) > 0;
  const theme = useTheme();
  const { t } = useTranslation("common");

  const menuItems: PopperMenuItem[] = [
    { id: "rename", label: t("rename"), icon: ICON_NAME.EDIT },
    { id: "share", label: t("share"), icon: ICON_NAME.SHARE },
    { id: "delete", label: t("delete"), icon: ICON_NAME.TRASH, color: theme.palette.error.main },
  ];

  return (
    <Paper
        elevation={0}
        onClick={() => onClick(folder)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 1.5,
          width: fullWidth ? "100%" : 190,
          cursor: "pointer",
          border: "1px solid",
          borderColor: selected ? "primary.main" : "divider",
          borderRadius: 2,
          bgcolor: selected ? "primary.light" : "background.paper",
          "&:hover": { borderColor: "primary.main", bgcolor: selected ? "primary.light" : "action.hover" },
          transition: "border-color 0.15s, background-color 0.15s",
          position: "relative",
        }}>
        <Tooltip
          title={showRoleChip && folder.role
            ? (folder.is_owned ? t("owner") : folder.role === "folder-editor" ? t("write_access") : t("read_access"))
            : ""}
          placement="top"
          arrow
          disableHoverListener={!showRoleChip || !folder.role}>
          <Box sx={{ position: "relative", display: "inline-flex", flexShrink: 0 }}>
            <Icon
              iconName={ICON_NAME.FOLDER}
              fontSize="small"
              htmlColor={selected ? theme.palette.primary.main : theme.palette.text.secondary}
            />
            {showRoleChip && folder.role && (
              <Box
                sx={{
                  position: "absolute",
                  bottom: -3,
                  right: -5,
                  bgcolor: "background.paper",
                  borderRadius: "50%",
                  lineHeight: 0,
                  p: "1px",
                }}>
                <Icon
                  iconName={folder.is_owned ? ICON_NAME.CROWN : folder.role === "folder-editor" ? ICON_NAME.EDIT : ICON_NAME.EYE}
                  style={{ fontSize: 10, color: theme.palette.text.secondary }}
                />
              </Box>
            )}
          </Box>
        </Tooltip>
        <Stack direction="row" alignItems="center" sx={{ overflow: "hidden", flex: 1, minWidth: 0, gap: 1 }}>
          <Typography
            variant="body2"
            noWrap
            sx={{ fontWeight: selected ? 700 : 400, color: selected ? "primary.main" : "text.primary", flex: 1, minWidth: 0 }}>
            {folder.name}
          </Typography>
          {isShared && (
            <Tooltip title={t("shared")} placement="top" arrow>
              <Box sx={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
                <Icon iconName={ICON_NAME.USERS} style={{ fontSize: 10, color: theme.palette.text.secondary }} />
              </Box>
            </Tooltip>
          )}
        </Stack>
        {/* Only show actions on owned non-home folders */}
        {enableActions && folder.is_owned && onMenuSelect && (
          <MoreMenu
            menuItems={menuItems}
            menuButton={
              <IconButton size="small" sx={{ ml: "auto", flexShrink: 0 }}>
                <Icon iconName={ICON_NAME.MORE_VERT} style={{ fontSize: 14 }} />
              </IconButton>
            }
            onSelect={(item) => onMenuSelect(item, folder)}
          />
        )}
      </Paper>
  );
}
