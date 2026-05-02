"use client";

import {
  Box,
  Breadcrumbs,
  Button,
  ClickAwayListener,
  Container,
  Grid,
  Link,
  ListItemIcon,
  Menu,
  MenuItem,
  MenuList,
  Pagination,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useFolders } from "@/lib/api/folders";
import { useLayers } from "@/lib/api/layers";
import { useTeams } from "@/lib/api/teams";
import { useOrganization } from "@/lib/api/users";
import type { PaginatedQueryParams } from "@/lib/validations/common";
import type { Folder } from "@/lib/validations/folder";
import type { GetDatasetSchema } from "@/lib/validations/layer";

import { AddLayerSourceType } from "@/types/common";

import { useAuthZ } from "@/hooks/auth/AuthZ";
import { useJobStatus } from "@/hooks/jobs/JobStatus";

import ContentSearchBar from "@/components/dashboard/common/ContentSearchbar";
import FolderCard from "@/components/dashboard/common/FolderCard";
import FoldersTreeView from "@/components/dashboard/common/FoldersTreeView";
import TileGrid from "@/components/dashboard/common/TileGrid";
import type { SelectedFolderForEdit } from "@/components/modals/Folder";
import FolderModal from "@/components/modals/Folder";
import ShareModal from "@/components/modals/Share";
import DatasetExternal from "@/components/modals/DatasetExternal";
import DatasetUploadModal from "@/components/modals/DatasetUpload";
import type { PopperMenuItem } from "@/components/common/PopperMenu";

type FolderEditModal = {
  type: "update" | "delete";
  selectedFolder: SelectedFolderForEdit;
  open: boolean;
};

const Datasets = () => {
  const router = useRouter();
  const { t } = useTranslation("common");
  const [queryParams, setQueryParams] = useState<PaginatedQueryParams>({
    order: "descendent",
    order_by: "updated_at",
    size: 12,
    page: 1,
  });
  const [datasetSchema, setDatasetSchema] = useState<GetDatasetSchema>({});
  const [view, setView] = useState<"list" | "grid">("grid");

  const { folders, mutate: mutateFolders } = useFolders({});
  const { teams } = useTeams();
  const { organization } = useOrganization();
  const { isOrgEditor } = useAuthZ();

  const homeFolder = useMemo(() => folders?.find((f) => f.is_owned && f.name === "home"), [folders]);

  // When browsing "My Content" root (no folder selected), restrict to the home
  // folder so layers moved into named folders don't bleed into the root view.
  const effectiveDatasetSchema = useMemo<GetDatasetSchema>(() => {
    if (!datasetSchema.folder_id && !queryParams.team_id && !queryParams.organization_id && homeFolder) {
      return { ...datasetSchema, folder_id: homeFolder.id };
    }
    return datasetSchema;
  }, [datasetSchema, queryParams.team_id, queryParams.organization_id, homeFolder]);

  const {
    mutate,
    layers: datasets,
    isLoading: isDatasetLoading,
    isError: _isDatasetError,
  } = useLayers(queryParams, effectiveDatasetSchema);

  useJobStatus(mutate, mutate);

  const [addDatasetModal, setAddDatasetModal] = useState<AddLayerSourceType | null>(null);
  const [addDatasetAnchorEl, setAddDatasetAnchorEl] = useState<null | HTMLElement>(null);
  const [folderEditModal, setFolderEditModal] = useState<FolderEditModal | undefined>();
  const [shareFolder, setShareFolder] = useState<Folder | null>(null);

  const open = Boolean(addDatasetAnchorEl);
  const handleAddDatasetClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    setAddDatasetAnchorEl(event.currentTarget);
  };
  const handleAddDatasetClose = () => {
    setAddDatasetAnchorEl(null);
  };

  const openAddDatasetModal = (sourceType: AddLayerSourceType) => {
    handleAddDatasetClose();
    setAddDatasetModal(sourceType);
  };

  const closeAddDatasetModal = () => {
    setAddDatasetModal(null);
    mutate();
  };

  const addDatasetMenuItems = [
    {
      sourceType: AddLayerSourceType.DatasourceUpload,
      iconName: ICON_NAME.UPLOAD,
      label: t("dataset_upload"),
    },
    {
      sourceType: AddLayerSourceType.DataSourceExternal,
      iconName: ICON_NAME.LINK,
      label: t("dataset_external"),
    },
  ];

  useEffect(() => {
    if (datasets?.pages && queryParams?.page && datasets?.pages < queryParams?.page) {
      setQueryParams({
        ...queryParams,
        page: datasets.pages,
      });
    }
  }, [datasets, queryParams]);

  // Determine what context we're in
  const activeFolderId = datasetSchema.folder_id;
  const activeTeamId = queryParams.team_id;
  const activeOrgId = queryParams.organization_id;
  const isMyContent = !activeTeamId && !activeOrgId;
  const showFolders = !activeFolderId;

  const activeFolderObj = useMemo(
    () => (activeFolderId ? folders?.find((f) => f.id === activeFolderId) : undefined),
    [folders, activeFolderId]
  );

  const activeTeamName = useMemo(
    () => teams?.find((t) => t.id === activeTeamId)?.name,
    [teams, activeTeamId]
  );
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

  const handleFolderClick = (folder: Folder) => {
    setDatasetSchema({ ...datasetSchema, folder_id: folder.id });
    setQueryParams({ ...queryParams, page: 1 });
  };

  const handleBackToMyContent = () => {
    const { folder_id: _, ...rest } = datasetSchema;
    setDatasetSchema(rest);
    setQueryParams({ ...queryParams, page: 1 });
  };

  const handleFolderMenuSelect = (menuItem: PopperMenuItem, folder: Folder) => {
    if (menuItem.id === "share") {
      setShareFolder(folder);
    } else {
      setFolderEditModal({
        type: menuItem.id === "rename" ? "update" : "delete",
        selectedFolder: { id: folder.id, name: folder.name },
        open: true,
      });
    }
  };

  return (
    <Container sx={{ py: 10, px: 10 }} maxWidth="xl">
      {addDatasetModal === AddLayerSourceType.DatasourceUpload && (
        <DatasetUploadModal
          open={true}
          onClose={closeAddDatasetModal}
          defaultFolderId={activeFolderId ?? homeFolder?.id}
        />
      )}
      {addDatasetModal === AddLayerSourceType.DataSourceExternal && (
        <DatasetExternal open={true} onClose={closeAddDatasetModal} />
      )}
      {folderEditModal && (
        <FolderModal
          type={folderEditModal.type}
          open={folderEditModal.open}
          onClose={() => setFolderEditModal(undefined)}
          onEdit={() => {
            if (folderEditModal.type === "delete" && activeFolderId === folderEditModal.selectedFolder.id) {
              handleBackToMyContent();
            }
            mutateFolders();
            setFolderEditModal(undefined);
          }}
          existingFolderNames={folders?.filter((f) => f.id !== folderEditModal.selectedFolder?.id).map((f) => f.name)}
          selectedFolder={folderEditModal.selectedFolder}
        />
      )}
      {shareFolder && (
        <ShareModal
          type="folder"
          open={true}
          onClose={() => setShareFolder(null)}
          content={shareFolder}
        />
      )}

      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 8,
        }}>
        <Typography variant="h6">{t("datasets")}</Typography>
        {isOrgEditor && (
          <Button
            disableElevation={true}
            startIcon={<Icon iconName={ICON_NAME.PLUS} style={{ fontSize: 12 }} />}
            onClick={handleAddDatasetClick}>
            {t("add_dataset")}
          </Button>
        )}
        <Menu
          anchorEl={addDatasetAnchorEl}
          sx={{
            "& .MuiPaper-root": {
              boxShadow: "0px 0px 10px 0px rgba(58, 53, 65, 0.1)",
            },
          }}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
          transformOrigin={{ vertical: -5, horizontal: "center" }}
          open={open}
          MenuListProps={{
            "aria-labelledby": "basic-button",
            sx: { p: 0 },
          }}
          onClose={handleAddDatasetClose}>
          <Box>
            <ClickAwayListener onClickAway={handleAddDatasetClose}>
              <MenuList>
                {addDatasetMenuItems.map((item, index) => (
                  <MenuItem key={index} onClick={() => openAddDatasetModal(item.sourceType)}>
                    <ListItemIcon>
                      <Icon iconName={item.iconName} style={{ fontSize: "15px" }} />
                    </ListItemIcon>
                    <Typography variant="body2">{item.label}</Typography>
                  </MenuItem>
                ))}
              </MenuList>
            </ClickAwayListener>
          </Box>
        </Menu>
      </Box>
      <Grid container justifyContent="space-between" spacing={4}>
        <Grid item xs={12}>
          <ContentSearchBar
            contentType="layer"
            view={view}
            setView={setView}
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
        </Grid>
        <Grid item xs={3}>
          <Paper elevation={3} sx={{ backgroundImage: "none" }}>
            <FoldersTreeView
              queryParams={{ ...datasetSchema, team_id: queryParams.team_id, organization_id: queryParams.organization_id }}
              enableActions={isOrgEditor}
              hideMyContent={!isOrgEditor}
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
              }}
            />
          </Paper>
        </Grid>
        <Grid item xs={9}>
          {/* Breadcrumb when inside a folder */}
          {activeFolderId && (
            <Breadcrumbs sx={{ mb: 4 }}>
              <Link
                underline="hover"
                color="inherit"
                sx={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5 }}
                onClick={handleBackToMyContent}>
                <Icon iconName={ICON_NAME.CHEVRON_LEFT} style={{ fontSize: 12 }} />
                {isMyContent ? t("my_content") : activeTeamName ?? activeOrgName ?? "…"}
              </Link>
              <Typography color="text.primary">{activeFolderObj?.name ?? "…"}</Typography>
            </Breadcrumbs>
          )}

          {/* Folders section */}
          {showFolders && contextFolders.length > 0 && (
            <Box sx={{ mb: 6 }}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: "uppercase", letterSpacing: 0.5, fontSize: 11 }}>
                {t("folders")}
              </Typography>
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
                {contextFolders.map((folder) => (
                  <FolderCard
                    key={folder.id}
                    folder={folder}
                    enableActions={isOrgEditor && folder.is_owned}
                    showRoleChip={!isMyContent}
                    onClick={handleFolderClick}
                    onMenuSelect={handleFolderMenuSelect}
                  />
                ))}
              </Box>
            </Box>
          )}

          {/* Datasets section label when folders are also shown */}
          {showFolders && (
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: "uppercase", letterSpacing: 0.5, fontSize: 11 }}>
              {t("datasets")}
            </Typography>
          )}

          <TileGrid
            view={view}
            items={datasets?.items ?? []}
            isLoading={isDatasetLoading}
            type="layer"
            enableActions={isOrgEditor}
            onClick={(item) => {
              if (item && item.id) {
                router.push(`/datasets/${item.id}`);
              }
            }}
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
        </Grid>
      </Grid>
    </Container>
  );
};

export default Datasets;
