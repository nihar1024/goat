import { LoadingButton } from "@mui/lab";
import {
  Box,
  Breadcrumbs,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Link,
  Pagination,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useFolders } from "@/lib/api/folders";
import { useLayers } from "@/lib/api/layers";
import { addProjectLayers, useProject, useProjectLayers } from "@/lib/api/projects";
import { useTeams } from "@/lib/api/teams";
import { useOrganization } from "@/lib/api/users";
import type { PaginatedQueryParams } from "@/lib/validations/common";
import type { Folder } from "@/lib/validations/folder";
import type { GetDatasetSchema, Layer } from "@/lib/validations/layer";
import type { Project } from "@/lib/validations/project";

import ContentSearchBar from "@/components/dashboard/common/ContentSearchbar";
import FolderCard from "@/components/dashboard/common/FolderCard";
import FoldersTreeView from "@/components/dashboard/common/FoldersTreeView";
import TileGrid from "@/components/dashboard/common/TileGrid";

interface DatasetExplorerProps {
  open: boolean;
  onClose?: () => void;
  projectId: string;
  /** Optional callback when a layer is selected. If provided, the layer won't be added to the project. */
  onLayerSelect?: (layer: Layer) => void;
}

const DatasetExplorerModal: React.FC<DatasetExplorerProps> = ({
  open,
  onClose,
  projectId,
  onLayerSelect,
}) => {
  const { t } = useTranslation("common");
  const [queryParams, setQueryParams] = useState<PaginatedQueryParams>({
    order: "descendent",
    order_by: "updated_at",
    size: 10,
    page: 1,
  });
  const [datasetSchema, setDatasetSchema] = useState<GetDatasetSchema>({});

  const { folders } = useFolders({});
  const { teams } = useTeams();
  const { organization } = useOrganization();

  const homeFolder = useMemo(() => folders?.find((f) => f.is_owned && f.name === "home"), [folders]);

  const activeFolderId = datasetSchema.folder_id;
  const activeTeamId = queryParams.team_id;
  const activeOrgId = queryParams.organization_id;
  const isMyContent = !activeTeamId && !activeOrgId;
  const showFolders = !activeFolderId;

  const activeFolderObj = useMemo(
    () => (activeFolderId ? folders?.find((f) => f.id === activeFolderId) : undefined),
    [folders, activeFolderId]
  );
  const activeTeamName = useMemo(() => teams?.find((t) => t.id === activeTeamId)?.name, [teams, activeTeamId]);
  const activeOrgName = organization?.name;

  const contextFolders = useMemo(() => {
    if (!folders) return [];
    if (isMyContent) return folders.filter((f) => f.is_owned && f.name !== "home");
    if (activeTeamId)
      return folders.filter(
        (f) =>
          (!f.is_owned && f.shared_from_name === activeTeamName) ||
          (f.is_owned && f.shared_with_ids?.includes(activeTeamId))
      );
    if (activeOrgId)
      return folders.filter(
        (f) =>
          (!f.is_owned && f.shared_from_name === activeOrgName) ||
          (f.is_owned && f.shared_with_ids?.includes(activeOrgId))
      );
    return [];
  }, [folders, isMyContent, activeTeamId, activeTeamName, activeOrgId, activeOrgName]);

  // At "My Content" root restrict to home folder so layers in named folders don't bleed through.
  const effectiveDatasetSchema = useMemo<GetDatasetSchema>(() => {
    if (!datasetSchema.folder_id && !queryParams.team_id && !queryParams.organization_id && homeFolder) {
      return { ...datasetSchema, folder_id: homeFolder.id };
    }
    return datasetSchema;
  }, [datasetSchema, queryParams.team_id, queryParams.organization_id, homeFolder]);

  const {
    layers: datasets,
    isLoading: isDatasetLoading,
    isError: _isDatasetError,
  } = useLayers(queryParams, effectiveDatasetSchema);

  const [isBusy, setIsBusy] = useState(false);
  const { mutate: mutateProjectLayers } = useProjectLayers(projectId);
  const { mutate: mutateProject } = useProject(projectId);

  const [selectedDataset, setSelectedDataset] = useState<Layer>();

  const handleFolderClick = (folder: Folder) => {
    setDatasetSchema({ ...datasetSchema, folder_id: folder.id });
    setQueryParams({ ...queryParams, page: 1 });
    setSelectedDataset(undefined);
  };

  const handleBackToRoot = () => {
    const { folder_id: _, ...rest } = datasetSchema;
    setDatasetSchema(rest);
    setQueryParams({ ...queryParams, page: 1 });
    setSelectedDataset(undefined);
  };

  const handleOnClose = () => {
    onClose && onClose();
  };

  const handleOnAdd = async () => {
    try {
      if (!selectedDataset) return;

      if (onLayerSelect) {
        onLayerSelect(selectedDataset);
        handleOnClose();
        return;
      }

      setIsBusy(true);
      await addProjectLayers(projectId, [selectedDataset.id]);
      mutateProjectLayers();
      mutateProject();
    } catch (error) {
      toast.error(t("error_adding_layer"));
    } finally {
      setIsBusy(false);
      handleOnClose();
    }
  };

  return (
    <>
      <Dialog open={open} onClose={handleOnClose} fullWidth maxWidth="md">
        <DialogTitle>{t("dataset_explorer")}</DialogTitle>
        <DialogContent>
          <Box sx={{ width: "100%" }}>
            <Grid container justifyContent="space-between" spacing={4}>
              <Grid item xs={4}>
                <Paper elevation={0} sx={{ backgroundImage: "none" }}>
                  <FoldersTreeView
                    queryParams={{ ...datasetSchema, team_id: queryParams.team_id, organization_id: queryParams.organization_id }}
                    setQueryParams={(params, teamId, organizationId) => {
                      const newQueryParams = { ...queryParams, page: 1 };
                      delete newQueryParams.team_id;
                      delete newQueryParams.organization_id;
                      if (teamId) {
                        newQueryParams.team_id = teamId;
                      } else if (organizationId) {
                        newQueryParams.organization_id = organizationId;
                      }
                      setQueryParams(newQueryParams);
                      const { team_id: _t, organization_id: _o, ...schemaParams } = params as Record<string, unknown>;
                      setDatasetSchema(schemaParams as GetDatasetSchema);
                      setSelectedDataset(undefined);
                    }}
                  />
                </Paper>
              </Grid>
              <Grid item xs={8}>
                <ContentSearchBar
                  contentType="layer"
                  view="list"
                  queryParams={queryParams}
                  setQueryParams={(queryParams) => {
                    setQueryParams({
                      ...queryParams,
                      page: 1,
                    });
                  }}
                  datasetSchema={datasetSchema}
                  setDatasetSchema={(datasetSchema) => {
                    setDatasetSchema(datasetSchema);
                    setQueryParams({
                      ...queryParams,
                      page: 1,
                    });
                  }}
                />

                {/* Breadcrumb when inside a folder */}
                {activeFolderId && (
                  <Breadcrumbs sx={{ mt: 2, mb: 1 }}>
                    <Link
                      underline="hover"
                      color="inherit"
                      sx={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5 }}
                      onClick={handleBackToRoot}>
                      <Icon iconName={ICON_NAME.CHEVRON_LEFT} style={{ fontSize: 12 }} />
                      {isMyContent ? t("my_content") : activeTeamName ?? activeOrgName ?? "…"}
                    </Link>
                    <Typography color="text.primary" variant="body2">{activeFolderObj?.name ?? "…"}</Typography>
                  </Breadcrumbs>
                )}

                <Stack direction="column" sx={{ mt: 2 }}>
                  {/* Folder cards at root */}
                  {showFolders && contextFolders.length > 0 && (
                    <Box sx={{ mb: 3 }}>
                      <Typography
                        variant="overline"
                        color="text.secondary"
                        sx={{ mb: 1.5, display: "block", lineHeight: 1 }}>
                        {t("folders")}
                      </Typography>
                      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1 }}>
                        {contextFolders.map((folder) => (
                          <FolderCard
                            key={folder.id}
                            folder={folder}
                            enableActions={false}
                            showRoleChip={!isMyContent}
                            fullWidth
                            onClick={handleFolderClick}
                          />
                        ))}
                      </Box>
                    </Box>
                  )}

                  {/* Datasets label when folders are also shown */}
                  {showFolders && (
                    <Typography
                      variant="overline"
                      color="text.secondary"
                      sx={{ mb: 1.5, display: "block", lineHeight: 1 }}>
                      {t("datasets")}
                    </Typography>
                  )}

                  <TileGrid
                    view="list"
                    enableActions={false}
                    selected={selectedDataset}
                    onClick={(item: Project | Layer) => {
                      if (item.id === selectedDataset?.id) {
                        setSelectedDataset(undefined);
                      } else {
                        setSelectedDataset(item as Layer);
                      }
                    }}
                    items={datasets?.items ?? []}
                    isLoading={isDatasetLoading}
                    type="layer"
                  />

                  {!isDatasetLoading && datasets && datasets?.items.length > 0 && (
                    <Stack direction="row" justifyContent="center" alignItems="center" sx={{ p: 4 }}>
                      <Pagination
                        count={datasets.pages || 1}
                        size="large"
                        page={queryParams.page || 1}
                        onChange={(_e, page) => {
                          setQueryParams({
                            ...queryParams,
                            page,
                          });
                        }}
                      />
                    </Stack>
                  )}
                </Stack>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions
          disableSpacing
          sx={{
            pt: 6,
            pb: 2,
            justifyContent: "flex-end",
          }}>
          <Stack direction="row" spacing={2}>
            <Button onClick={handleOnClose} variant="text">
              <Typography variant="body2" fontWeight="bold">
                {t("cancel")}
              </Typography>
            </Button>
            <LoadingButton
              loading={isBusy}
              variant="contained"
              color="primary"
              onClick={handleOnAdd}
              disabled={!selectedDataset || isDatasetLoading}>
              {t("add_layer")}
            </LoadingButton>
          </Stack>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default DatasetExplorerModal;
