import { MAX_EDITABLE_LAYER_SIZE } from "@/lib/constants";

export type CanEditLayerFeaturesArgs = {
  /** Id of the signed-in user. */
  currentUserId?: string | null;
  /** Owner of the underlying dataset (`projectLayer.user_id`). */
  layerOwnerId?: string | null;
  /** Owner of the project the layer is viewed in (`project.owned_by.id`). */
  projectOwnerId?: string | null;
  /** Whether the user holds project-owner/project-editor on this project. */
  isProjectEditor: boolean;
  /** Dataset size in bytes; layers above the limit are not editable. */
  layerSize?: number | null;
  /** Catalog layers are read-only regardless of role. */
  inCatalog?: boolean | null;
};

/**
 * Whether to offer feature editing for a layer in a project.
 *
 * Mirrors the server rule (geoapi `LayerService.user_can_edit_layer`): the
 * owner may always edit, and a project editor may edit a layer whose owner
 * also edits that project.
 *
 * The client cannot see whether a *third* collaborator holds an edit grant,
 * so it approximates "layer owner is also an editor here" as "layer owner is
 * the project owner". That under-approximates: a layer contributed by another
 * collaborator shows no edit action even though the server would allow it.
 * Erring this way hides an action rather than surfacing one that 403s.
 */
export function canEditLayerFeatures({
  currentUserId,
  layerOwnerId,
  projectOwnerId,
  isProjectEditor,
  layerSize,
  inCatalog,
}: CanEditLayerFeaturesArgs): boolean {
  if (!isProjectEditor || inCatalog) return false;
  if (layerSize && layerSize > MAX_EDITABLE_LAYER_SIZE) return false;
  if (!currentUserId || !layerOwnerId) return false;

  if (layerOwnerId === currentUserId) return true;
  return !!projectOwnerId && layerOwnerId === projectOwnerId;
}
