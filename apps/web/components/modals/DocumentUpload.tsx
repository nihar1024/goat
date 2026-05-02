import LoadingButton from "@mui/lab/LoadingButton";
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
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { getWritableFolders, useFolders } from "@/lib/api/folders";
import { uploadAsset } from "@/lib/api/assets";
import type { Folder } from "@/lib/validations/folder";
import { DOCUMENT_ACCEPT, DOCUMENTS_MAX_FILE_SIZE_MiB } from "@/lib/validations/assets";

import FolderSelect from "@/components/dashboard/common/FolderSelect";

interface DocumentUploadProps {
  open: boolean;
  onClose: () => void;
  defaultFolderId?: string;
  onSuccess?: () => void;
}

export default function DocumentUploadModal({
  open,
  onClose,
  defaultFolderId,
  onSuccess,
}: DocumentUploadProps) {
  const { t } = useTranslation("common");
  const { folders: allFolders } = useFolders({});
  const writableFolders = getWritableFolders(allFolders);

  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync default folder once writable folders load
  useEffect(() => {
    if (defaultFolderId && writableFolders) {
      const folder = writableFolders.find((f) => f.id === defaultFolderId) ?? null;
      setSelectedFolder(folder);
    }
  }, [defaultFolderId, writableFolders]);

  const acceptAttr = Object.values(DOCUMENT_ACCEPT).flat().join(",");

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file && file.size > DOCUMENTS_MAX_FILE_SIZE_MiB * 1024 * 1024) {
      toast.error(`File too large. Maximum size is ${DOCUMENTS_MAX_FILE_SIZE_MiB} MiB.`);
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || !selectedFolder) return;
    try {
      setIsBusy(true);
      await uploadAsset(selectedFile, "document", { folderId: selectedFolder.id });
      toast.success(t("document_upload_success"));
      onSuccess?.();
      handleClose();
    } catch {
      toast.error(t("error_uploading_document"));
    } finally {
      setIsBusy(false);
    }
  };

  const handleClose = () => {
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>{t("upload_document")}</DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ mt: 1 }}>
          <FolderSelect
            folders={writableFolders}
            selectedFolder={selectedFolder}
            setSelectedFolder={setSelectedFolder}
          />
          <Box>
            <input
              ref={fileInputRef}
              type="file"
              accept={acceptAttr}
              style={{ display: "none" }}
              id="document-file-input"
              onChange={handleFileChange}
            />
            <label htmlFor="document-file-input">
              <Button variant="outlined" component="span" fullWidth>
                {selectedFile ? selectedFile.name : t("select_file")}
              </Button>
            </label>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
              PDF, DOCX, DOC — max {DOCUMENTS_MAX_FILE_SIZE_MiB} MiB
            </Typography>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={handleClose} variant="text">
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <LoadingButton
          loading={isBusy}
          variant="contained"
          onClick={handleUpload}
          disabled={!selectedFile || !selectedFolder}>
          {t("upload")}
        </LoadingButton>
      </DialogActions>
    </Dialog>
  );
}
