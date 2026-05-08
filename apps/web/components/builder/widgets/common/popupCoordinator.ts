/**
 * Cross-instance coordination for popup widgets (InfoChip, Links, etc.).
 *
 * Each rich text or links widget maintains its own state for "which popup is
 * open here". Without coordination, two instances of the same widget rendered
 * on the page (editor pane + preview pane, or two dashboards) can each have an
 * open popup at the same time — visually overlapping.
 *
 * Whenever a popup opens, the caller emits a `popup:open` event. All other
 * popup hosts listen and close their own state if the event's `id` doesn't
 * match their own.
 */

const EVENT_NAME = "goat:popup:open";

export interface PopupOpenDetail {
  /** Unique id of the popup that just opened. Anything else with a different id should close. */
  id: number;
}

export function emitPopupOpen(id: number): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<PopupOpenDetail>(EVENT_NAME, { detail: { id } }));
}

export function onPopupOpenElsewhere(
  ownId: () => number | null,
  closeMine: () => void
): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = (e: Event) => {
    const detail = (e as CustomEvent<PopupOpenDetail>).detail;
    const mine = ownId();
    if (mine !== null && detail.id !== mine) {
      closeMine();
    }
  };
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}
