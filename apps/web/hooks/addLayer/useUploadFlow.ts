import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type FieldErrors, type UseFormRegister, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { requestDatasetUpload } from "@/lib/api/datasets";
import { getWritableFolders, useFolders } from "@/lib/api/folders";
import { createLayer } from "@/lib/api/layers";
import { useJobs } from "@/lib/api/processes";
import { useProject } from "@/lib/api/projects";
import { uploadFileToS3 } from "@/lib/services/s3";
import { setRunningJobIds } from "@/lib/store/jobs/slice";
import { parseTabularPreview, type TabularPreview } from "@/lib/utils/tabular-preview";
import type { GetContentQueryParams } from "@/lib/validations/common";
import type { Folder } from "@/lib/validations/folder";
import type { LayerMetadata } from "@/lib/validations/layer";
import { createLayerFromDatasetSchema, layerMetadataSchema } from "@/lib/validations/layer";

import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import type { FlowController } from "@/hooks/addLayer/flow";

/**
 * Uploading a file as a dataset: state, steps, validation and submit — no UI.
 *
 * Headless so the flow is not tied to the modal that hosts it today; a side panel
 * or a page can mount this with a body of its own. Everything the host draws
 * (frame, stepper, footer) it draws from `FlowController`.
 *
 * The API sequence is unchanged from the dialog this replaces: presigned URL →
 * direct S3 upload → `createLayer`, whose OGC job id goes to the jobs store.
 */

const ACCEPTED_FILE_TYPES = [".gpkg", ".geojson", ".zip", ".kml", ".csv", ".xlsx", ".parquet"];
const TABULAR_EXTENSIONS = ["csv", "xlsx", "xls"];

export type UploadFlowState = {
  file?: File;
  fileError?: string;
  setFile: (file: File | null) => void;
  acceptedFileTypes: string[];
  /** Writable folders, and the one this dataset lands in. */
  folders?: Folder[];
  selectedFolder?: Folder | null;
  setSelectedFolder: (folder: Folder | null) => void;
  /** CSV/XLSX only: the parsed head of the file plus how to read it. */
  isTabular: boolean;
  preview: TabularPreview | null;
  hasHeader: boolean;
  setHasHeader: (value: boolean) => void;
  sheet: string;
  setSheet: (value: string) => void;
  /** Metadata form, validated by `layerMetadataSchema`. */
  register: UseFormRegister<LayerMetadata>;
  errors: FieldErrors<LayerMetadata>;
  /** Defaults the name field to the file's own name, without its extension. */
  suggestedName: string;
  values: LayerMetadata;
};

export type UploadFlow = FlowController & { upload: UploadFlowState };

export const useUploadFlow = ({
  projectId,
  defaultFolderId,
  onDone,
}: {
  projectId?: string;
  defaultFolderId?: string;
  onDone?: () => void;
}): UploadFlow => {
  const { t } = useTranslation("common");
  const dispatch = useAppDispatch();
  const runningJobIds = useAppSelector((state) => state.jobs.runningJobIds);

  const { project } = useProject(projectId);
  const { mutate: mutateJobs } = useJobs({ read: false });
  const queryParams: GetContentQueryParams = { order: "descendent", order_by: "updated_at" };
  const { folders: allFolders } = useFolders(queryParams);
  const folders = getWritableFolders(allFolders);

  const [step, setStep] = useState(0);
  const [file, setFileValue] = useState<File>();
  const [fileError, setFileError] = useState<string>();
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>();
  const folderInitialized = useRef(false);
  const [isBusy, setIsBusy] = useState(false);
  const [preview, setPreview] = useState<TabularPreview | null>(null);
  const [hasHeader, setHasHeader] = useState(true);
  const [sheet, setSheet] = useState("");

  const isTabular = useMemo(() => {
    const ext = file?.name.split(".").pop()?.toLowerCase();
    return !!ext && TABULAR_EXTENSIONS.includes(ext);
  }, [file]);

  /** A tabular file earns an extra step to configure how it is read. */
  const steps = useMemo(() => {
    const base = [t("select_file"), t("destination_and_metadata"), t("confirmation")];
    return isTabular ? [base[0], t("preview_and_configure"), base[1], base[2]] : base;
  }, [isTabular, t]);

  const metadataStep = isTabular ? 2 : 1;
  const lastStep = steps.length - 1;

  // The project's own folder is the natural destination; otherwise whatever folder
  // the host was looking at.
  useEffect(() => {
    if (!folders || folderInitialized.current) return;
    const projectFolder = folders.find((folder) => folder.id === project?.folder_id);
    if (projectFolder) {
      setSelectedFolder(projectFolder);
      folderInitialized.current = true;
      return;
    }
    if (defaultFolderId) {
      const fallback = folders.find((folder) => folder.id === defaultFolderId);
      if (fallback) {
        setSelectedFolder(fallback);
        folderInitialized.current = true;
      }
    }
  }, [folders, project?.folder_id, defaultFolderId]);

  useEffect(() => {
    if (!file || !isTabular) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    parseTabularPreview(file, { hasHeader, sheetName: sheet || undefined })
      .then((parsed) => {
        if (cancelled) return;
        setPreview(parsed);
        if (!sheet && parsed.sheetNames.length > 0) setSheet(parsed.sheetNames[0]);
      })
      .catch((error) => {
        console.error("Preview parse error:", error);
        if (!cancelled) setPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [file, isTabular, hasHeader, sheet]);

  const {
    register,
    getValues,
    watch,
    reset: resetForm,
    formState: { errors, isValid },
  } = useForm<LayerMetadata>({ mode: "onChange", resolver: zodResolver(layerMetadataSchema) });
  // Watched, not read once: the confirmation step has to re-render as the fields change.
  const values = watch();

  const suggestedName = useMemo(() => {
    if (!file) return "";
    const ext = file.name.split(".").pop();
    return ext && ACCEPTED_FILE_TYPES.includes(`.${ext}`)
      ? file.name.replace(`.${ext}`, "")
      : file.name;
  }, [file]);

  const setFile = useCallback((next: File | null) => {
    setFileError(undefined);
    setFileValue(undefined);
    if (!next?.name) return;
    if (!ACCEPTED_FILE_TYPES.some((type) => next.name.endsWith(type))) {
      setFileError("Invalid file type. Please select a file of type");
      return;
    }
    setFileValue(next);
  }, []);

  const reset = useCallback(() => {
    setStep(0);
    setFileValue(undefined);
    setFileError(undefined);
    setIsBusy(false);
    setPreview(null);
    setHasHeader(true);
    setSheet("");
    setSelectedFolder(undefined);
    folderInitialized.current = false;
    resetForm();
  }, [resetForm]);

  const submit = useCallback(async () => {
    if (!file) return;
    try {
      setIsBusy(true);
      const presigned = await requestDatasetUpload({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
      });
      await uploadFileToS3(file, presigned);
      const payload = createLayerFromDatasetSchema.parse({
        ...getValues(),
        folder_id: selectedFolder?.id,
        s3_key: presigned.fields.key,
        ...(isTabular && { has_header: hasHeader }),
        ...(isTabular && sheet && { sheet_name: sheet }),
      });
      const response = await createLayer(payload, projectId);
      const jobId = response?.jobID;
      if (jobId) {
        mutateJobs();
        dispatch(setRunningJobIds([...runningJobIds, jobId]));
      }
    } catch (error) {
      toast.error(t("error_uploading_dataset"));
      console.error("error", error);
    } finally {
      reset();
      onDone?.();
    }
  }, [
    file,
    getValues,
    selectedFolder?.id,
    isTabular,
    hasHeader,
    sheet,
    projectId,
    mutateJobs,
    dispatch,
    runningJobIds,
    t,
    reset,
    onDone,
  ]);

  /**
   * What the host's primary control says and does. Each step states its own
   * blocking condition, so no host has to know the rules.
   */
  const action = useMemo(() => {
    if (step < lastStep) {
      const blocked =
        (step === 0 && !file) || (step === metadataStep && (!isValid || !selectedFolder));
      return {
        label: t("next"),
        disabled: blocked,
        run: () => setStep((current) => current + 1),
      };
    }
    return { label: t("upload"), disabled: isBusy, run: submit };
  }, [step, lastStep, metadataStep, file, isValid, selectedFolder, isBusy, submit, t]);

  return {
    steps,
    step,
    goTo: setStep,
    action,
    isBusy,
    reset,
    upload: {
      file,
      fileError,
      setFile,
      acceptedFileTypes: ACCEPTED_FILE_TYPES,
      folders,
      selectedFolder,
      setSelectedFolder,
      isTabular,
      preview,
      hasHeader,
      setHasHeader,
      sheet,
      setSheet,
      register,
      errors,
      suggestedName,
      values,
    },
  };
};
