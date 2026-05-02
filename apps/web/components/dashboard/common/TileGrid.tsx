import { Box, Grid, Skeleton } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import type { Layer } from "@/lib/validations/layer";
import type { Folder } from "@/lib/validations/folder";
import type { Project } from "@/lib/validations/project";

import { ContentActions } from "@/types/common";

import { useContentMoreMenu } from "@/hooks/dashboard/ContentHooks";

import EmptySection from "@/components/common/EmptySection";
import TileCard from "@/components/dashboard/common/TileCard";
import ContentDialogWrapper from "@/components/modals/ContentDialogWrapper";

interface TileGridProps {
  view: "list" | "grid";
  type: "project" | "layer";
  items: Omit<Project, "layer_order">[] | Layer[];
  isLoading: boolean;
  enableActions?: boolean;
  onClick?: (item: Project | Layer) => void;
  onAction?: (action: ContentActions, item: Project | Layer) => void;
  selected?: Project | Layer;
  /** Pass folders + currentUserId to show ownership/access role chips on cards */
  folders?: Folder[];
  currentUserId?: string;
  activeTeamId?: string;
  activeOrgId?: string;
}

const ROLE_CHIP_OWNER = { icon: ICON_NAME.CROWN, tooltip: "Owner" };
const ROLE_CHIP_WRITE = { icon: ICON_NAME.EDIT, tooltip: "Editor" };
const ROLE_CHIP_READ = { icon: ICON_NAME.EYE, tooltip: "Viewer" };

function getRoleChip(
  item: Project | Layer,
  folders: Folder[] | undefined,
  currentUserId: string | undefined,
  activeTeamId?: string,
  activeOrgId?: string,
) {
  if (!currentUserId) return undefined;

  // Owner check
  if ((item as Project).owned_by?.id === currentUserId) return ROLE_CHIP_OWNER;

  // Folder-grant path: look up folder role
  if (folders) {
    const folder = folders.find((f) => f.id === (item as { folder_id?: string }).folder_id);
    if (folder) {
      if (folder.is_owned) return ROLE_CHIP_OWNER;
      if (folder.role === "folder-editor") return ROLE_CHIP_WRITE;
      if (folder.role === "folder-viewer") return ROLE_CHIP_READ;
    }
  }

  // Fallback: item shared individually via team/org link.
  // In team/org context the backend returns exactly one shared_with entry
  // for the current team/org, so [0] is safe.
  const sharedWith = (item as { shared_with?: { teams?: { role?: string }[]; organizations?: { role?: string }[] } }).shared_with;
  if (activeTeamId && sharedWith?.teams?.length) {
    const role = sharedWith.teams[0]?.role;
    if (role?.endsWith("-editor")) return ROLE_CHIP_WRITE;
    if (role?.endsWith("-viewer")) return ROLE_CHIP_READ;
  }
  if (activeOrgId && sharedWith?.organizations?.length) {
    const role = sharedWith.organizations[0]?.role;
    if (role?.endsWith("-editor")) return ROLE_CHIP_WRITE;
    if (role?.endsWith("-viewer")) return ROLE_CHIP_READ;
  }

  return undefined;
}

const TileGrid = (props: TileGridProps) => {
  const { items, isLoading } = props;
  const { t } = useTranslation("common");
  const listProps = {
    xs: 12,
  };
  const gridProps = {
    xs: 12,
    sm: 6,
    md: 4,
    lg: 3,
  };

  const NON_DIALOG_ACTIONS = new Set([ContentActions.EXPORT, ContentActions.DUPLICATE]);

  const { getMoreMenuOptions, activeContent, moreMenuState, closeMoreMenu, openMoreMenu } =
    useContentMoreMenu();

  const handleMoreMenuSelect = (menuItem: Parameters<typeof openMoreMenu>[0], contentItem: Project | Layer) => {
    if (NON_DIALOG_ACTIONS.has(menuItem.id as ContentActions) && props.onAction) {
      props.onAction(menuItem.id as ContentActions, contentItem);
      return;
    }
    openMoreMenu(menuItem, contentItem);
  };

  return (
    <>
      {activeContent && moreMenuState && (
        <>
          <ContentDialogWrapper
            content={activeContent}
            action={moreMenuState.id as ContentActions}
            onClose={closeMoreMenu}
            onContentDelete={closeMoreMenu}
            type={props.type}
          />
        </>
      )}

      <Box
        sx={{
          ...(props.view === "list" && {
            boxShadow: props.enableActions ? 3 : 0,
          }),
        }}>
        <Grid container spacing={props.view === "list" ? 0 : 5}>
          {!isLoading && items?.length === 0 && (
            <Grid item xs={12}>
              <EmptySection
                label={props.type === "project" ? t("no_projects_found") : t("no_datasets_found")}
                icon={props.type === "project" ? ICON_NAME.MAP : ICON_NAME.DATABASE}
              />
            </Grid>
          )}
          {(isLoading ? Array.from(new Array(4)) : (items ?? [])).map(
            (item: Project | Layer, index: number) => (
              <Grid
                item
                onClick={() => {
                  if (props.onClick) {
                    props.onClick(item);
                  }
                }}
                key={item?.id ?? index}
                {...(props.view === "list" ? listProps : gridProps)}>
                {!item ? (
                  <Skeleton variant="rectangular" height={props.view === "list" ? 80 : 200} />
                ) : (
                  <TileCard
                    selected={props.selected}
                    enableActions={props.enableActions}
                    cardType={props.view}
                    item={item}
                    moreMenuOptions={getMoreMenuOptions(props.type, item, props.currentUserId)}
                    onMoreMenuSelect={handleMoreMenuSelect}
                    roleChip={getRoleChip(item, props.folders, props.currentUserId, props.activeTeamId, props.activeOrgId)}
                  />
                )}
              </Grid>
            )
          )}
        </Grid>
      </Box>
    </>
  );
};

export default TileGrid;
