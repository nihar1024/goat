import { MAX_EDITABLE_LAYER_SIZE } from "@/lib/constants";

export type CanEditLayerFieldsArgs = {
  /** Id of the signed-in user. */
  currentUserId?: string | null;
  /** Owner of the underlying dataset (`projectLayer.user_id`). */
  layerOwnerId?: string | null;
  /** Owner of the project the layer is viewed in (`project.owned_by.id`). */
  projectOwnerId?: string | null;
  /** Whether the user holds project-owner/project-editor on this project. */
  isProjectEditor: boolean;
  /** Catalog layers are read-only regardless of role. */
  inCatalog?: boolean | null;
};

export type CanEditLayerFeaturesArgs = CanEditLayerFieldsArgs & {
  /** Dataset size in bytes; layers above the limit are not editable. */
  layerSize?: number | null;
};

/**
 * Whether to offer changing a layer's fields — adding, renaming or deleting a
 * column, and editing field display config.
 *
 * Mirrors the server rule the `/collections/{id}/columns` endpoints apply
 * (geoapi `_get_authorized_metadata` + `LayerService.user_can_edit_layer`):
 * a catalog layer is a shared read-only snapshot and every write to one is
 * refused with 403 "Catalog layers are read-only", so offering the action can
 * only produce an error toast. The owner may always edit, and a project editor
 * may edit a layer whose owner also edits that project.
 *
 * The client cannot see whether a *third* collaborator holds an edit grant,
 * so it approximates "layer owner is also an editor here" as "layer owner is
 * the project owner". That under-approximates: a layer contributed by another
 * collaborator shows no edit action even though the server would allow it.
 * Erring this way hides an action rather than surfacing one that 403s.
 */
export function canEditLayerFields({
  currentUserId,
  layerOwnerId,
  projectOwnerId,
  isProjectEditor,
  inCatalog,
}: CanEditLayerFieldsArgs): boolean {
  if (!isProjectEditor || inCatalog) return false;
  if (!currentUserId || !layerOwnerId) return false;

  if (layerOwnerId === currentUserId) return true;
  return !!projectOwnerId && layerOwnerId === projectOwnerId;
}

/**
 * Whether to offer feature editing for a layer in a project.
 *
 * Everything {@link canEditLayerFields} requires, plus a size cap: feature
 * editing loads the features into the browser, so beyond
 * `MAX_EDITABLE_LAYER_SIZE` it is not offered. Column operations run in the
 * database and carry no such limit.
 */
export function canEditLayerFeatures({
  layerSize,
  ...fields
}: CanEditLayerFeaturesArgs): boolean {
  if (!canEditLayerFields(fields)) return false;
  if (layerSize && layerSize > MAX_EDITABLE_LAYER_SIZE) return false;
  return true;
}
