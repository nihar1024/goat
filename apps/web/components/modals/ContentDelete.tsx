import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";
import { Trans } from "react-i18next";
import { toast } from "react-toastify";
import { mutate } from "swr";

import {
  DATASET_PACKAGES_API_BASE_URL,
  deleteDatasetPackage,
  isDatasetPackageTile,
} from "@/lib/api/dataset-packages";
import { LAYERS_API_BASE_URL, deleteLayer } from "@/lib/api/layers";
import { useJobs } from "@/lib/api/processes";
import { PROJECTS_API_BASE_URL, deleteProject } from "@/lib/api/projects";
import { setRunningJobIds } from "@/lib/store/jobs/slice";
import type { Layer } from "@/lib/validations/layer";

import type { ContentDialogBaseProps } from "@/types/dashboard/content";

import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

interface ContentDeleteDialogProps extends ContentDialogBaseProps {
  disabled?: boolean;
  onDelete?: () => void;
}

const ContentDeleteModal: React.FC<ContentDeleteDialogProps> = ({
  open,
  disabled,
  onClose,
  onDelete,
  type,
  content,
}) => {
  const { t } = useTranslation("common");
  const { mutate: mutateJobs } = useJobs({ read: false });
  const dispatch = useAppDispatch();
  const runningJobIds = useAppSelector((state) => state.jobs.runningJobIds);

  const isDatasetPackage = isDatasetPackageTile(content);

  const handleDelete = async () => {
    try {
      if (!content) return;
      if (isDatasetPackage) {
        // Dataset package: one call removes the package + all its member layers
        // (backend cascades DuckLake cleanup). Refresh the packages list.
        await deleteDatasetPackage(content.id);
        mutate((key) => key === DATASET_PACKAGES_API_BASE_URL);
        toast.success(t("delete_dataset_package_success"));
      } else if (type === "layer") {
        // Optimistic update: immediately remove layer from cache
        mutate(
          (key) => Array.isArray(key) && key[0] === LAYERS_API_BASE_URL,
          (currentData: { items: Layer[]; total: number; pages: number } | undefined) => {
            if (!currentData?.items) return currentData;
            return {
              ...currentData,
              items: currentData.items.filter((item) => item.id !== content.id),
              total: Math.max(0, currentData.total - 1),
            };
          },
          { revalidate: false }
        );

        // Start delete job in background
        const job = await deleteLayer(content?.id);
        if (job?.jobID) {
          // Track job only for error handling - success doesn't need UI update
          mutateJobs();
          dispatch(setRunningJobIds([...runningJobIds, job.jobID]));
        }
      } else if (type === "project") {
        await deleteProject(content?.id);
        mutate((key) => Array.isArray(key) && key[0] === PROJECTS_API_BASE_URL);
        toast.success(t("delete_project_success"));
      }
    } catch {
      // Revert optimistic update on error by revalidating
      if (isDatasetPackage) {
        mutate((key) => key === DATASET_PACKAGES_API_BASE_URL);
      } else if (type === "layer") {
        mutate((key) => Array.isArray(key) && key[0] === LAYERS_API_BASE_URL);
      }
      toast.error(
        isDatasetPackage
          ? t("delete_dataset_package_error")
          : type === "layer"
            ? t("delete_layer_error")
            : t("delete_project_error")
      );
    }

    onDelete?.();
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>
        {isDatasetPackage
          ? t("delete_dataset_package")
          : type === "layer"
            ? t("delete_layer")
            : t("delete_project")}
      </DialogTitle>
      <DialogContent>
        <DialogContentText>
          {isDatasetPackage ? (
            <Trans
              i18nKey="common:are_you_sure_to_delete_dataset_package"
              values={{ name: content?.name }}
              components={{ b: <b /> }}
            />
          ) : type === "layer" ? (
            <Trans
              i18nKey="common:are_you_sure_to_delete_layer"
              values={{ layer: content?.name }}
              components={{ b: <b /> }}
            />
          ) : (
            <Trans
              i18nKey="common:are_you_sure_to_delete_project"
              values={{ project: content?.name }}
              components={{ b: <b /> }}
            />
          )}
        </DialogContentText>
      </DialogContent>
      <DialogActions
        disableSpacing
        sx={{
          pb: 2,
        }}>
        <Button onClick={onClose} variant="text" sx={{ borderRadius: 0 }}>
          <Typography variant="body2" fontWeight="bold">
            {t("cancel")}
          </Typography>
        </Button>
        <Button
          onClick={handleDelete}
          variant="text"
          color="error"
          disabled={disabled}
          sx={{ borderRadius: 0 }}>
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("delete")}
          </Typography>
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ContentDeleteModal;
