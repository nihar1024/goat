import { Chip, IconButton, Paper, Stack, Tooltip, Typography, useTheme } from "@mui/material";
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
  onClick: (folder: Folder) => void;
  onMenuSelect?: (item: PopperMenuItem, folder: Folder) => void;
}

export default function FolderCard({ folder, selected, enableActions, showRoleChip, onClick, onMenuSelect }: FolderCardProps) {
  const theme = useTheme();
  const { t } = useTranslation("common");

  const menuItems: PopperMenuItem[] = [
    { id: "rename", label: t("rename"), icon: ICON_NAME.EDIT },
    { id: "share", label: t("share"), icon: ICON_NAME.SHARE },
    { id: "delete", label: t("delete"), icon: ICON_NAME.TRASH, color: theme.palette.error.main },
  ];

  return (
    <Tooltip title={folder.name} placement="top" disableInteractive>
      <Paper
        elevation={0}
        onClick={() => onClick(folder)}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 1.5,
          minWidth: 150,
          maxWidth: 220,
          cursor: "pointer",
          border: "1px solid",
          borderColor: selected ? "primary.main" : "divider",
          borderRadius: 2,
          bgcolor: selected ? "primary.light" : "background.paper",
          "&:hover": { borderColor: "primary.main", bgcolor: selected ? "primary.light" : "action.hover" },
          transition: "border-color 0.15s, background-color 0.15s",
          position: "relative",
        }}>
        <Icon
          iconName={ICON_NAME.FOLDER}
          fontSize="small"
          htmlColor={selected ? theme.palette.primary.main : theme.palette.text.secondary}
        />
        <Stack sx={{ overflow: "hidden", flex: 1, minWidth: 0 }}>
          <Typography
            variant="body2"
            noWrap
            sx={{ fontWeight: selected ? 700 : 400, color: selected ? "primary.main" : "text.primary" }}>
            {folder.name}
          </Typography>
          {showRoleChip && folder.role && (
            <>
              {/* Team / org source — only for folders shared to you */}
              {!folder.is_owned && folder.shared_from_name && (
                <Typography variant="caption" noWrap sx={{ color: "text.secondary", fontSize: "9px" }}>
                  {folder.shared_from_name}
                </Typography>
              )}
              <Chip
                label={
                  folder.is_owned
                    ? t("owner")
                    : folder.role === "folder-editor"
                    ? t("write_access")
                    : t("read_access")
                }
                size="small"
                sx={{
                  height: 16,
                  fontSize: "9px",
                  fontWeight: 500,
                  backgroundColor: folder.is_owned
                    ? "#F3E8FD"
                    : folder.role === "folder-editor"
                    ? "#E8F4FD"
                    : "#E2F5F4",
                  color: folder.is_owned ? "#7B1FA2" : folder.role === "folder-editor" ? "#1565C0" : "#1A857A",
                  alignSelf: "flex-start",
                  "& .MuiChip-label": { px: 0.75 },
                }}
              />
            </>
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
    </Tooltip>
  );
}
