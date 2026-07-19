/**
 * Popup ↔ layer-visibility reconciliation.
 *
 * A feature popup is bound to a specific layer, but its state (`popupInfo`)
 * lives in Redux independently of that layer's `properties.visibility`. When
 * the user toggles the owning layer off in the Layers panel (or deletes it),
 * nothing clears `popupInfo` — so the popup and its active-feature pulse would
 * otherwise stay stranded on a layer the map no longer draws. These pure
 * helpers let the map hosts decide when to dismiss such an orphaned popup.
 */

/** A ProjectLayer/Layer as far as popup visibility resolution is concerned. */
export interface PopupLayerLike {
  id: string | number;
  /** ProjectLayer carries the dataset id here; plain Layer leaves it unset. */
  layer_id?: string;
  properties?: { visibility?: boolean } | null;
}

/**
 * Find the layer that owns an open popup. `popupInfo.layerId` is set to
 * `layer_id ?? id` at dispatch time, so match against both — ProjectLayer
 * stores the dataset id on `layer_id` while a plain Layer uses `id`.
 */
export function findPopupLayer<T extends PopupLayerLike>(
  layerId: string | undefined,
  layers: T[] | undefined,
): T | undefined {
  if (!layerId || !layers) return undefined;
  return layers.find((l) => l.layer_id === layerId || l.id.toString() === layerId);
}

/**
 * True when an open popup should be dismissed because its owning layer is no
 * longer drawn on the map — either hidden (visibility toggled off) or removed
 * from the project.
 *
 * Returns false when `layers` is undefined (still loading / mid-refetch) so a
 * transient fetch never closes a valid popup, and false when there is no
 * `layerId` so non-layer-bound popups are left untouched. A missing
 * `visibility` flag counts as visible, matching how the map renders layers.
 */
export function shouldClosePopupForHiddenLayer(
  layerId: string | undefined,
  layers: PopupLayerLike[] | undefined,
): boolean {
  if (!layerId || !layers) return false;
  const layer = findPopupLayer(layerId, layers);
  if (!layer) return true; // owning layer was removed from the project
  return (layer.properties?.visibility ?? true) === false;
}
