import { Box } from "@mui/material";

import { useInfoChipPreviewClick } from "@/components/builder/widgets/common/useInfoChipPreviewClick";

interface WidgetTitleProps {
  title?: string;
}

/**
 * Read-only widget heading. The title is rendered as HTML (built via the
 * sidebar rich-text editor in WidgetCommonConfigs) and may contain info chips
 * and links — the click handler routes those through the shared popover.
 */
const WidgetTitle = ({ title }: WidgetTitleProps) => {
  const { containerRef, onClick, popover } = useInfoChipPreviewClick();

  if (!title || title.trim().length === 0) return null;

  return (
    <>
      <Box
        ref={containerRef}
        onClick={onClick}
        sx={(theme) => ({
          mb: 0.5,
          fontSize: "1rem",
          fontWeight: 700,
          lineHeight: 1.5,
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
        })}
        dangerouslySetInnerHTML={{ __html: title }}
      />
      {popover}
    </>
  );
};

export default WidgetTitle;
