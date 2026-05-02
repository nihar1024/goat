"use client";

import {
  Box,
  Breadcrumbs,
  Button,
  ButtonGroup,
  Container,
  Grid,
  Link,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Pagination,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useFolders } from "@/lib/api/folders";
import { executeProcessAsync } from "@/lib/api/processes";
import { copyProject, useProjects } from "@/lib/api/projects";
import { useTeams } from "@/lib/api/teams";
import { useOrganization } from "@/lib/api/users";
import { setRunningJobIds } from "@/lib/store/jobs/slice";
import type { Folder } from "@/lib/validations/folder";
import type { Layer } from "@/lib/validations/layer";
import type { Project } from "@/lib/validations/project";
import type { GetProjectsQueryParams } from "@/lib/validations/project";

import { ContentActions } from "@/types/common";

import { useAuthZ } from "@/hooks/auth/AuthZ";
import { useJobStatus } from "@/hooks/jobs/JobStatus";
import { useAppDispatch, useAppSelector } from "@/hooks/store/ContextHooks";

import ContentSearchBar from "@/components/dashboard/common/ContentSearchbar";
import FolderCard from "@/components/dashboard/common/FolderCard";
import FoldersTreeView from "@/components/dashboard/common/FoldersTreeView";
import TileGrid from "@/components/dashboard/common/TileGrid";
import type { SelectedFolderForEdit } from "@/components/modals/Folder";
import FolderModal from "@/components/modals/Folder";
import ProjectModal from "@/components/modals/Project";
import ProjectImportModal from "@/components/modals/ProjectImport";
import ShareModal from "@/components/modals/Share";
import type { PopperMenuItem } from "@/components/common/PopperMenu";

type FolderEditModal = {
  type: "update" | "delete";
  selectedFolder: SelectedFolderForEdit;
  open: boolean;
};

const Projects = () => {
  const router = useRouter();
  const [queryParams, setQueryParams] = useState<GetProjectsQueryParams>({
    order: "descendent",
    order_by: "updated_at",
    size: 12,
    page: 1,
  });
  const [view, setView] = useState<"list" | "grid">("grid");
  const { t } = useTranslation("common");

  const { folders, mutate: mutateFolders } = useFolders({});
  const { teams } = useTeams();
  const { organization } = useOrganization();

  const homeFolder = useMemo(() => folders?.find((f) => f.is_owned && f.name === "home"), [folders]);

  // When browsing "My Content" root (no folder selected), restrict to the home
  // folder so projects moved into named folders don't bleed into the root view.
  const effectiveQueryParams = useMemo<GetProjectsQueryParams>(() => {
    if (!queryParams.folder_id && !queryParams.team_id && !queryParams.organization_id && homeFolder) {
      return { ...queryParams, folder_id: homeFolder.id };
    }
    return queryParams;
  }, [queryParams, homeFolder]);

  const { projects, isLoading: isProjectLoading, isError: _isProjectError, mutate } = useProjects(effectiveQueryParams);

  const [openProjectModal, setOpenProjectModal] = useState(false);
  const [openImportModal, setOpenImportModal] = useState(false);
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [folderEditModal, setFolderEditModal] = useState<FolderEditModal | undefined>();
  const [shareFolder, setShareFolder] = useState<Folder | null>(null);
  const { isOrgEditor } = useAuthZ();
  const dispatch = useAppDispatch();
  const runningJobIds = useAppSelector((state) => state.jobs.runningJobIds);
  useJobStatus(mutate, mutate);

  const handleProjectAction = useCallback(
    async (action: ContentActions, item: Project | Layer) => {
      const project = item as Project;
      if (action === ContentActions.DUPLICATE) {
        try {
          const newProject = await copyProject(project.id);
          toast.success(t("project_duplicated"));
          mutate();
          if (newProject?.id) {
            router.push(`/map/${newProject.id}`);
          }
        } catch (_error) {
          toast.error(t("error_duplicating_project"));
        }
      } else if (action === ContentActions.EXPORT) {
        try {
          const job = await executeProcessAsync("project_export", {
            project_id: project.id,
          });
          if (job?.jobID) {
            dispatch(setRunningJobIds([...runningJobIds, job.jobID]));
          }
          toast.info(t("project_export_submitted"));
        } catch (_error) {
          toast.error(t("error_exporting_project"));
        }
      }
    },
    [mutate, router, t]
  );

  useEffect(() => {
    if (projects?.pages && queryParams?.page && projects?.pages < queryParams?.page) {
      setQueryParams({ ...queryParams, page: projects.pages });
    }
  }, [projects, queryParams]);

  // Determine what context we're in
  const activeFolderId = queryParams.folder_id;
  const activeTeamId = queryParams.team_id;
  const activeOrgId = queryParams.organization_id;
  const isMyContent = !activeTeamId && !activeOrgId;
  const showFolders = !activeFolderId;

  // Find the active folder object for the breadcrumb label
  const activeFolderObj = useMemo(
    () => (activeFolderId ? folders?.find((f) => f.id === activeFolderId) : undefined),
    [folders, activeFolderId]
  );

  const activeTeamName = useMemo(
    () => teams?.find((t) => t.id === activeTeamId)?.name,
    [teams, activeTeamId]
  );
  const activeOrgName = organization?.name;

  // Folders filtered to the active context
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
    setQueryParams({ ...queryParams, folder_id: folder.id, page: 1 });
  };

  const handleBackToMyContent = () => {
    const { folder_id: _, ...rest } = queryParams;
    setQueryParams({ ...rest, page: 1 });
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
      <ProjectModal
       
        open={openProjectModal}
        onClose={() => setOpenProjectModal(false)}
        defaultFolderId={activeFolderId ?? homeFolder?.id}
      />
      <ProjectImportModal
        open={openImportModal}
        onClose={() => setOpenImportModal(false)}
        onImportStarted={() => {}}
      />
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

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 8 }}>
        <Typography variant="h6">{t("projects")}</Typography>
        {isOrgEditor && (
          <>
            <ButtonGroup variant="contained" disableElevation sx={{ "& .MuiButtonGroup-grouped:not(:last-of-type)": { borderColor: "white" } }}>
              <Button
                startIcon={<Icon iconName={ICON_NAME.PLUS} style={{ fontSize: 12 }} />}
                onClick={() => setOpenProjectModal(true)}>
                {t("new_project")}
              </Button>
              <Button size="small" onClick={(e) => setAnchorEl(e.currentTarget)}>
                <Icon iconName={ICON_NAME.CHEVRON_DOWN} style={{ fontSize: 10 }} />
              </Button>
            </ButtonGroup>
            <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
              <MenuItem onClick={() => { setAnchorEl(null); setOpenImportModal(true); }}>
                <ListItemIcon>
                  <Icon iconName={ICON_NAME.UPLOAD} style={{ fontSize: 14 }} />
                </ListItemIcon>
                <ListItemText>{t("import_project")}</ListItemText>
              </MenuItem>
            </Menu>
          </>
        )}
      </Box>

      <Grid container justifyContent="space-between" spacing={4}>
        <Grid item xs={12}>
          <ContentSearchBar
            contentType="project"
            view={view}
            setView={setView}
            queryParams={queryParams}
            setQueryParams={(queryParams) => setQueryParams({ ...queryParams, page: 1 })}
          />
        </Grid>
        <Grid item xs={3}>
          <Paper elevation={3}>
            <FoldersTreeView
              queryParams={queryParams}
              enableActions={isOrgEditor}
              hideMyContent={!isOrgEditor}
              setQueryParams={(params, teamId, organizationId) => {
                const newQueryParams = { ...params, page: 1 };
                delete newQueryParams?.["team_id"];
                delete newQueryParams?.["organization_id"];
                if (teamId) newQueryParams["team_id"] = teamId;
                else if (organizationId) newQueryParams["organization_id"] = organizationId;
                setQueryParams(newQueryParams);
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

          {/* Projects section label when folders are also shown */}
          {showFolders && (
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2, textTransform: "uppercase", letterSpacing: 0.5, fontSize: 11 }}>
              {t("projects")}
            </Typography>
          )}

          <TileGrid
            view={view}
            items={projects?.items ?? []}
            enableActions={isOrgEditor}
            isLoading={isProjectLoading}
            type="project"
            onClick={(item) => { if (item?.id) router.push(`/map/${item.id}`); }}
            onAction={handleProjectAction}
          />
          {!isProjectLoading && projects && projects?.items.length > 0 && (
            <Stack direction="row" justifyContent="center" alignItems="center" sx={{ p: 4 }}>
              <Pagination
                count={projects.pages || 1}
                size="large"
                page={queryParams.page || 1}
                onChange={(_e, page) => setQueryParams({ ...queryParams, page })}
              />
            </Stack>
          )}
        </Grid>
      </Grid>
    </Container>
  );
};

export default Projects;
