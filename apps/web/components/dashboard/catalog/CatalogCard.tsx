"use client";

import { Box, Collapse, IconButton, Paper, Stack, Typography, useTheme } from "@mui/material";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { CatalogCardModel } from "@/lib/catalog/card";

import { useCatalogLabels } from "@/hooks/catalog/useCatalogLabels";

import CatalogBundleMembers from "@/components/dashboard/catalog/CatalogBundleMembers";
import { Meta, TypeTag } from "@/components/dashboard/catalog/CatalogCardParts";
import CatalogThumbnail from "@/components/dashboard/catalog/CatalogThumbnail";

/** One result: thumbnail with the kind tagged over it, title with a save star, two clamped lines of
 * description, and a meta row of publisher / licence / language / period. */

type CatalogCardProps = {
  card: CatalogCardModel;
  view?: "list" | "grid";
  onClick?: () => void;
  /** Opens one layer from the inline expand. */
  onOpenMember?: (memberId: string) => void;
  starred?: boolean;
  onToggleStar?: () => void;
  /**
   * Phone layout: a square mark beside the title instead of a thumbnail band, the
   * kind as a text eyebrow, and the description clamped to one line.
   */
  compact?: boolean;
};

const CatalogCard = ({
  card,
  view = "list",
  onClick,
  onOpenMember,
  starred = false,
  onToggleStar,
  compact,
}: CatalogCardProps) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const labels = useCatalogLabels();
  const [hover, setHover] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const { kind, memberCount } = card;
  const isBundle = kind === "bundle";
  // A phone is one column wide, so grid and list would render identically —
  // compact wins over both.
  const isGrid = view === "grid" && !compact;
  // A tile and a phone card are both about half a row wide, so their meta cells
  // pair up two per line instead of standing in one.
  const twoUp = isGrid || !!compact;

  // No tag at all when the kind is genuinely unknown: labelling every such item
  // "Feature" would be a guess presented as fact.
  const typeLabel = labels.kindLabel(kind);

  // The meta row keeps one order in every view, most-populated first, so only the
  // tail of it can be missing.
  const language = labels.languageLabel(card.languageCode);
  const period = labels.formatPeriod(card.period);
  const license = labels.licenseLabel(card.license);
  const meta = [
    card.publisher && { icon: ICON_NAME.ORGANIZATION, label: card.publisher },
    license && { icon: ICON_NAME.LICENSE, label: license },
    language && { icon: ICON_NAME.LANGUAGE, label: language },
    period && { icon: ICON_NAME.CALENDAR, label: period },
  ].filter((cell): cell is { icon: ICON_NAME; label: string } => !!cell);

  /** One save control, placed differently on a row and on a tile. */
  const star = onToggleStar ? (
    <IconButton
      size="small"
      aria-label={t("save")}
      onClick={(event) => {
        // The whole card navigates to the dataset; saving must not.
        event.stopPropagation();
        onToggleStar();
      }}
      sx={{
        flexShrink: 0,
        opacity: hover || starred ? 1 : 0.55,
        transition: theme.transitions.create("opacity"),
        // No disc behind it on a tile.
      }}>
      <Icon
        iconName={ICON_NAME.STAR}
        style={{ fontSize: 15 }}
        htmlColor={starred ? theme.palette.primary.main : theme.palette.text.secondary}
      />
    </IconButton>
  ) : null;

  return (
    <Paper
      elevation={0}
      onClick={() => onClick?.()}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      sx={{
        position: "relative",
        overflow: "hidden",
        borderRadius: "12px",
        border: `1.5px solid ${hover ? theme.palette.primary.main : theme.palette.divider}`,
        boxShadow: hover ? theme.shadows[4] : theme.shadows[6],
        transform: hover ? "translateY(-2px)" : "none",
        transition: theme.transitions.create(
          ["transform", "box-shadow", "border-color"],
          { duration: 140 }
        ),
        cursor: onClick ? "pointer" : "default",
        height: isGrid ? "100%" : undefined,
        // A floor, so a grid row stays even when one card has less to show.
        // dataset has no description.
        minHeight: isGrid ? 320 : undefined,
      }}>
      <Box
        sx={{
          display: "grid",
          // The body column has to fill the card for the meta row's `mt: auto` to mean anything — otherwise the grid is only as tall as its content and the divider sits directly under the title.
          height: isGrid ? "100%" : undefined,
          gridTemplateRows: isGrid ? "auto minmax(0, 1fr)" : undefined,
          gridTemplateColumns: compact
            ? "44px minmax(0, 1fr)"
            : {
                xs: "minmax(0, 1fr)",
                sm: isGrid ? "minmax(0, 1fr)" : "200px minmax(0, 1fr)",
              },
          gap: compact ? "12px" : isGrid ? "10px" : "18px",
          p: compact ? 3 : isGrid ? 3 : 4,
        }}>
        <Box
          sx={{
            position: "relative",
            width: isGrid ? "100%" : "fit-content",
          }}>
          <CatalogThumbnail
            kind={kind}
            geometryType={card.geometryType}
            memberCount={memberCount}
            href={card.thumbnailHref}
            variant={compact ? "mark" : isGrid ? "grid" : "list"}
          />
          {typeLabel && !compact && (
            <Box sx={{ position: "absolute", top: 8, left: 8 }}>
              <TypeTag label={typeLabel} />
            </Box>
          )}
          {/* On a tile the star sits over the thumbnail: the title is two clamped lines and cannot give up the width. */}
          {isGrid && star && (
            <Box sx={{ position: "absolute", top: 4, right: 4 }}>{star}</Box>
          )}
        </Box>

        <Stack sx={{ minWidth: 0 }}>
          <Stack
            direction="row"
            alignItems="flex-start"
            justifyContent="space-between"
            spacing={3}
            sx={{ mb: isGrid ? 2 : 0 }}>
            <Box sx={{ minWidth: 0 }}>
              {compact && typeLabel && (
                <Typography
                  sx={{
                    fontSize: 10.5,
                    fontWeight: 700,
                    letterSpacing: 0.6,
                    textTransform: "uppercase",
                    color: theme.palette.text.secondary,
                    mb: 0.5,
                  }}>
                  {typeLabel}
                </Typography>
              )}
            <Typography
              fontWeight={700}
              sx={{
                minWidth: 0,
                fontSize: compact ? 14 : isGrid ? 14 : 16,
                letterSpacing: "-0.1px",
                lineHeight: 1.3,
                overflowWrap: "anywhere",
                ...(isGrid || compact
                  ? {
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }
                  : {}),
              }}>
              {card.title}
            </Typography>
            </Box>
            {!isGrid && star}
          </Stack>

          {card.description && (
            <Typography
              color="text.secondary"
              sx={{
                mt: 1,
                mb: compact ? 1.5 : 3,
                maxWidth: 920,
                fontSize: compact ? 12 : isGrid ? 12 : 13,
                lineHeight: 1.55,
                display: "-webkit-box",
                WebkitLineClamp: compact ? 1 : 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}>
              {card.description}
            </Typography>
          )}

          {meta.length > 0 && (
            <Box
              sx={{
                mt: compact ? 2 : "auto",
                // A clear gap above the rule even when the title fills the card.
                pt: isGrid ? 3 : 2.5,
                borderTop: `1px solid ${theme.palette.divider}`,
                // Spread across the rule, ends flush with it: the cells divide the width they actually have instead of filling the first N of four fixed columns, which left the last cell stranded three-quarters across and a quarter of the rule with nothing under it.
                display: "grid",
                gridTemplateColumns: `repeat(${meta.length}, minmax(0, auto))`,
                justifyContent: "space-between",
                columnGap: isGrid ? 1.5 : 4,
                rowGap: 1.5,
                // A tile is half the width of a row, so its cells pair up two per line instead of being squeezed into one.
                ...(twoUp && { gridTemplateColumns: "minmax(0, 1fr) auto" }),
              }}>
              {meta.map((cell, index) => (
                <Meta
                  key={`${cell.icon}-${cell.label}`}
                  icon={cell.icon}
                  label={cell.label}
                  sx={
                    twoUp
                      ? {
                          // Right-hand cells sit against the right edge; a final cell with no partner takes the whole line rather than half of it, which is what left "since 2010" stranded under a truncated publisher.
                          ...(index % 2 === 1 && { justifySelf: "end" }),
                          ...(index === meta.length - 1 &&
                            meta.length % 2 === 1 && { gridColumn: "1 / -1" }),
                        }
                      : undefined
                  }
                />
              ))}
            </Box>
          )}
        </Stack>
      </Box>

      {/* Rows only: a footer on a tile would stretch every card in its grid row to match. */}
      {isBundle && !isGrid && card.bundleId && (
        <>
          <Box
            component="button"
            type="button"
            onClick={(event: React.MouseEvent) => {
              event.stopPropagation();
              setExpanded((open) => !open);
            }}
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              width: "100%",
              px: 5,
              py: 2.5,
              font: "inherit",
              cursor: "pointer",
              border: "none",
              borderTop: `1px solid ${theme.palette.divider}`,
              backgroundColor: theme.palette.action.hover,
              "&:hover": { backgroundColor: theme.palette.action.selected },
            }}>
            <Typography variant="body2" color="text.secondary" fontWeight={500}>
              {t("catalog_member_count", { count: memberCount })}
            </Typography>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Typography variant="body2" color="primary" fontWeight={600}>
                {expanded ? t("collapse") : t("expand")}
              </Typography>
              <Icon
                iconName={expanded ? ICON_NAME.CHEVRON_UP : ICON_NAME.CHEVRON_DOWN}
                style={{ fontSize: 14 }}
                htmlColor={theme.palette.primary.main}
              />
            </Stack>
          </Box>
          <Collapse in={expanded} unmountOnExit>
            <CatalogBundleMembers collectionId={card.bundleId} onOpenMember={onOpenMember} />
          </Collapse>
        </>
      )}
    </Paper>
  );
};

export default CatalogCard;
