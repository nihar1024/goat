import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Box, Divider, Link, Stack, Typography } from "@mui/material";
import { Fragment, useState } from "react";

import type { LinksElementSchema } from "@/lib/validations/widget";

import MarkdownPopupDialog from "@/components/builder/widgets/common/MarkdownPopupDialog";

const LinksElementWidget = ({ config }: { config: LinksElementSchema }) => {
  const { setup, options } = config;
  const links = setup?.links ?? [];
  const showExternalIcon = options?.show_external_icon ?? true;
  const openInNewTab = options?.open_in_new_tab ?? true;
  const copyrightText = options?.secondary_text;
  const separator = options?.separator ?? "vertical_line";
  const [openPopupIndex, setOpenPopupIndex] = useState<number | null>(null);

  if (links.length === 0 && !copyrightText) {
    return null;
  }

  return (
    <Box sx={{ width: "100%" }}>
      {setup?.title && (
        <Typography variant="body1" fontWeight="bold" align="left" gutterBottom>
          {setup.title}
        </Typography>
      )}
      <Stack direction="row" flexWrap="wrap" alignItems="center" sx={{ gap: 0 }}>
        {links.map((link, index) => (
          <Fragment key={index}>
            {index > 0 &&
              (separator === "vertical_line" ? (
                <Divider
                  orientation="vertical"
                  flexItem
                  sx={{ mx: 1, alignSelf: "center", height: 14 }}
                />
              ) : (
                <Typography
                  variant="caption"
                  sx={{ mx: 1, color: "text.disabled", userSelect: "none" }}>
                  {separator === "dot" ? "·" : "–"}
                </Typography>
              ))}
            {link.link_type === "popup" ? (
              <Link
                component="button"
                variant="body2"
                color="text.secondary"
                underline="hover"
                onClick={() => setOpenPopupIndex(index)}
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  whiteSpace: "nowrap",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  "&:hover": { color: "primary.main" },
                }}>
                {link.label}
                <ArticleOutlinedIcon sx={{ fontSize: 13, color: "text.disabled" }} />
              </Link>
            ) : (
              <Link
                href={link.url}
                variant="body2"
                color="text.secondary"
                underline="hover"
                {...(openInNewTab && { target: "_blank", rel: "noopener noreferrer" })}
                sx={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  whiteSpace: "nowrap",
                  "&:hover": { color: "primary.main" },
                }}>
                {link.label}
                {showExternalIcon && (
                  <OpenInNewIcon sx={{ fontSize: 13, color: "text.disabled" }} />
                )}
              </Link>
            )}
          </Fragment>
        ))}
        {copyrightText && (
          <Typography
            variant="caption"
            sx={{ ml: "auto", color: "text.disabled", whiteSpace: "nowrap" }}>
            {copyrightText}
          </Typography>
        )}
      </Stack>
      {options?.description && (
        <Typography variant="body2" align="left">
          {options.description}
        </Typography>
      )}

      {links.map((link, index) =>
        link.link_type === "popup" && link.popup_content ? (
          <MarkdownPopupDialog
            key={index}
            open={openPopupIndex === index}
            onClose={() => setOpenPopupIndex(null)}
            title={link.label}
            content={link.popup_content}
          />
        ) : null
      )}
    </Box>
  );
};

export default LinksElementWidget;
