import { Box } from "@mui/material";
import type { SxProps, Theme } from "@mui/material";

import { useInfoChipPreviewClick } from "@/components/builder/widgets/common/useInfoChipPreviewClick";

interface WidgetDescriptionProps {
  description?: string;
  sx?: SxProps<Theme>;
}

/**
 * Read-only widget description. Built by the sidebar rich-text editor and
 * rendered here as HTML; routes info-chip and link clicks through the shared
 * popover.
 */
const WidgetDescription = ({ description, sx }: WidgetDescriptionProps) => {
  const { containerRef, onClick, popover } = useInfoChipPreviewClick();

  if (!description || description.trim().length === 0) return null;
  return (
    <>
      <Box
        ref={containerRef}
        onClick={onClick}
        sx={[
          (theme) => ({
            fontSize: "0.875rem",
            lineHeight: 1.5,
            color: theme.palette.text.secondary,
            "& p": { margin: 0 },
            "& a": { color: theme.palette.primary.main, textDecoration: "underline" },
            "& .info-chip": {
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 14,
              height: 14,
              borderRadius: "50%",
              border: `1.5px solid ${theme.palette.grey[500]}`,
              backgroundColor: "transparent",
              color: theme.palette.grey[500],
              fontSize: 9,
              fontWeight: 700,
              fontStyle: "normal",
              fontFamily: "serif",
              lineHeight: 1,
              cursor: "pointer",
              userSelect: "none",
              verticalAlign: "middle",
              marginInline: "2px",
              boxSizing: "border-box",
            },
          }),
          ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
        ]}
        dangerouslySetInnerHTML={{ __html: description }}
      />
      {popover}
    </>
  );
};

export default WidgetDescription;
