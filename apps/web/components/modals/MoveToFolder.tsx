import { LoadingButton } from "@mui/lab";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import { mutate } from "swr";

import { getWritableFolders, useFolders } from "@/lib/api/folders";
import { LAYERS_API_BASE_URL, updateDataset } from "@/lib/api/layers";
import { PROJECTS_API_BASE_URL, updateProject } from "@/lib/api/projects";
import type { GetContentQueryParams } from "@/lib/validations/common";
import type { Folder } from "@/lib/validations/folder";
import type { Layer, PostDataset } from "@/lib/validations/layer";
import type { PostProject, Project } from "@/lib/validations/project";

import FolderSelect from "@/components/dashboard/common/FolderSelect";

interface ContentMoveToFolderDialogProps {
  open: boolean;
  onClose?: () => void;
  disabled?: boolean;
  type: "project" | "layer";
  onContentMove?: () => void;
  content: Layer | Project;
}

const ContentMoveToFolderModal: React.FC<ContentMoveToFolderDialogProps> = ({
  open,
  onClose,
  disabled,
  type,
  onContentMove,
  content,
}) => {
  const { t } = useTranslation("common");
  const queryParams: GetContentQueryParams = {
    order: "descendent",
    order_by: "updated_at",
  };
  const { folders: allFolders } = useFolders(queryParams);
  const folders = getWritableFolders(allFolders);

  const [isBusy, setIsBusy] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);

  useEffect(() => {
    if (allFolders && selectedFolder === null) {
      const folderId = content.folder_id;
      const match = allFolders.find((folder) => folder.id === folderId);
      if (match && match.is_owned && match.name !== "home") {
        setSelectedFolder(match);
      }
    }
  }, [content.folder_id, allFolders]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMoveToFolder = async () => {
    try {
      if (!content) return;
      setIsBusy(true);
      const payload = {
        folder_id: selectedFolder?.id,
      };
      if (type === "layer") {
        payload["id"] = content.id;
        await updateDataset(content.id, payload as PostDataset);
        mutate((key) => Array.isArray(key) && key[0] === LAYERS_API_BASE_URL);
      } else if (type === "project") {
        await updateProject(content.id, payload as PostProject);
        mutate((key) => Array.isArray(key) && key[0] === PROJECTS_API_BASE_URL);
      }
    } catch {
      toast.error(`${t("error_moving_content")} ${content.name}`);
    } finally {
      setIsBusy(false);
      onClose?.();
    }

    onContentMove?.();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{`${t("move_to")}`}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ py: 2 }}>
          <Box>
            <FolderSelect
              folders={folders}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions
        disableSpacing
        sx={{
          pb: 2,
        }}>
        <Button onClick={onClose} variant="text">
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <LoadingButton
          loading={isBusy}
          onClick={handleMoveToFolder}
          disabled={disabled || !selectedFolder || selectedFolder.id === content.folder_id}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("move")}
          </Typography>
        </LoadingButton>
      </DialogActions>
    </Dialog>
  );
};

export default ContentMoveToFolderModal;
