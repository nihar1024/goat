import { useCallback, useEffect, useRef, useState } from "react";

import {
  emitPopupOpen,
  onPopupOpenElsewhere,
} from "@/components/builder/widgets/common/popupCoordinator";
import { InfoChipViewPopover } from "@/components/builder/widgets/common/InfoChipPopover";

type PopupType = "tooltip" | "popover" | "dialog";
type PopupPlacement = "top" | "bottom" | "left" | "right" | "auto";
type PopupSize = "sm" | "md" | "lg";

interface ViewPopoverState {
  openId: number;
  chipId: string;
  anchorEl: HTMLElement;
  text: string;
  url?: string;
  title?: string;
  popup_type: PopupType;
  placement: PopupPlacement;
  size: PopupSize;
}

/**
 * Adds info-chip + link interactivity to any read-only HTML container that
 * was produced by the rich text editor.
 *
 * Returns:
 *   - `containerRef`: attach to the element holding the rendered HTML.
 *   - `onClick`: React click handler that opens the chip popover or follows
 *     the link.
 *   - `popover`: React node — render after the container so the InfoChipViewPopover
 *     mounts when a chip is clicked.
 */
export function useInfoChipPreviewClick() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [viewPopover, setViewPopover] = useState<ViewPopoverState | null>(null);

  // Close our popover when another popup opens elsewhere on the page.
  useEffect(() => {
    return onPopupOpenElsewhere(
      () => viewPopover?.openId ?? null,
      () => setViewPopover(null)
    );
  }, [viewPopover?.openId]);

  const onClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const chip = target.closest(".info-chip") as HTMLElement | null;
    if (chip) {
      e.preventDefault();
      e.stopPropagation();
      const text = chip.getAttribute("data-info-text") || "";
      const url = chip.getAttribute("data-info-url") || undefined;
      const title = chip.getAttribute("data-info-title") || undefined;
      const popup_type = (chip.getAttribute("data-popup-type") || "popover") as PopupType;
      const placement = (chip.getAttribute("data-placement") || "auto") as PopupPlacement;
      const size = (chip.getAttribute("data-popup-size") || "md") as PopupSize;
      const chipId = chip.getAttribute("data-info-id") || "";
      // Virtual anchor: re-resolves the live chip each measurement so that
      // dangerouslySetInnerHTML re-renders don't leave a stale (detached)
      // anchor pointing the popper at the top-left corner.
      const virtualAnchor = {
        getBoundingClientRect: () => {
          const liveChip = chipId
            ? (containerRef.current?.querySelector(
                `[data-info-id="${chipId}"]`
              ) as HTMLElement | null)
            : null;
          return (liveChip ?? chip).getBoundingClientRect();
        },
      } as unknown as HTMLElement;
      const openId = Date.now();
      setViewPopover({
        openId,
        chipId,
        anchorEl: virtualAnchor,
        text,
        url,
        title,
        popup_type,
        placement,
        size,
      });
      emitPopupOpen(openId);
      return;
    }
    const link = target.closest("a") as HTMLAnchorElement | null;
    if (link?.href) {
      e.preventDefault();
      e.stopPropagation();
      window.open(link.href, "_blank", "noopener,noreferrer");
    }
  }, []);

  const popover = viewPopover ? (
    <InfoChipViewPopover
      key={viewPopover.openId}
      anchorEl={viewPopover.anchorEl}
      text={viewPopover.text}
      url={viewPopover.url}
      title={viewPopover.title}
      popup_type={viewPopover.popup_type}
      placement={viewPopover.placement}
      size={viewPopover.size}
      onClose={() => setViewPopover(null)}
    />
  ) : null;

  return { containerRef, onClick, popover };
}
