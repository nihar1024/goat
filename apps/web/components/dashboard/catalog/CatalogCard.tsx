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

/**
 * One result in the catalog, following the prototype's `ListCard`/`GridCard`
 * (`catalog.jsx`): a thumbnail with the kind tagged over it, a title carrying a
 * save star, two clamped lines of description, and a meta row of
 * publisher / licence / language / data period.
 *
 * Purely presentational: it renders a `CatalogCardModel` and never asks what that
 * model was built from. The list builds one per dataset (a STAC Collection), a
 * bundle's page builds one per layer (a STAC Item) — see `lib/catalog/card`.
 *
 * Nothing assumes a field is populated. Coverage in the live catalog is uneven, so
 * every cell renders only with content and the grid shrinks rather than showing
 * dashes.
 *
 * A dataset of several layers grows a footer that reveals them inline, so what a
 * bundle contains can be seen without leaving the list.
 */

type CatalogCardProps = {
  card: CatalogCardModel;
  view?: "list" | "grid";
  onClick?: () => void;
  /** Opens one layer from the inline expand. */
  onOpenMember?: (memberId: string) => void;
  starred?: boolean;
  onToggleStar?: () => void;
  /**
   * Phone layout: a small square mark beside the title instead of a full-width
   * thumbnail band, the kind as a text eyebrow instead of a tag over the image,
   * and the description clamped to one line.
   *
   * Measured against CARTO's mobile catalog, which fits about five datasets on a
   * phone screen where a banded card fits two — and the band is a generic glyph
   * today, so it is decoration standing between the reader and the next result.
   * The description was dropped entirely at first, when items carried none; now
   * that every dataset has one, a single line is worth more than the space it
   * costs.
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

  /**
   * The meta row, in one order for every view — **most-populated first**, so the
   * cells that are always there anchor the left edge and only the tail can be
   * missing. A row that led with a field 18% of datasets lack (`language`, as the
   * prototype has it) put a gap in the first column of every fifth card, and the
   * remaining cells slid left, so no two rows in the list lined up.
   *
   * Coverage over the catalog's 3,834 datasets, which is what fixed the order:
   * publisher 100%, a stated period 100%, language 81%, a *named* licence 4%
   * (`licenseLabel` drops the 3,659 that say `other`). The prototype's other four
   * cells are gone, with the reasons recorded in `lib/catalog/card`.
   *
   * The grid tile takes the same fields in the same order, two per row instead of
   * four. A tile and a row describing the same dataset should not disagree about
   * what is worth knowing about it.
   */
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
        // No disc behind it on a tile. The stand-in thumbnail is a flat slate
        // ground, not a photograph, so a white circle only added a shape nobody
        // could name. Reinstate a scrim if real images ever land behind the star.
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
        boxShadow: hover ? theme.shadows[3] : theme.shadows[1],
        transform: hover ? "translateY(-2px)" : "none",
        transition: theme.transitions.create(
          ["transform", "box-shadow", "border-color"],
          { duration: 140 }
        ),
        cursor: onClick ? "pointer" : "default",
        height: isGrid ? "100%" : undefined,
        // The prototype's tile keeps a floor so a grid row stays even when one
        // dataset has no description.
        minHeight: isGrid ? 320 : undefined,
      }}>
      <Box
        sx={{
          display: "grid",
          // The body column has to fill the card for the meta row's `mt: auto` to
          // mean anything — otherwise the grid is only as tall as its content and
          // the divider sits directly under the title.
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
          {/* On a tile the star sits over the thumbnail, as the prototype's
              GridCard has it: the title is two clamped lines and cannot give up
              the width a control beside it would take. */}
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
                // Spread across the rule, ends flush with it: the cells divide the
                // width they actually have instead of filling the first N of four
                // fixed columns, which left the last cell stranded three-quarters
                // across and a quarter of the rule with nothing under it. Since a
                // card carries 2–4 cells depending on what its dataset published,
                // fixed columns cannot be both full-width and gap-free — this
                // distributes whatever is there.
                display: "grid",
                gridTemplateColumns: `repeat(${meta.length}, minmax(0, auto))`,
                justifyContent: "space-between",
                columnGap: isGrid ? 1.5 : 4,
                rowGap: 1.5,
                // A tile is half the width of a row, so its cells pair up two per
                // line instead of being squeezed into one. `1fr auto` rather than
                // two equal halves: the left cell takes the room it needs (a
                // publisher name is long, a language is one word) and the right
                // one is pushed to the edge, so both ends meet the rule the way
                // they do on a row.
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
                          // Right-hand cells sit against the right edge; a final
                          // cell with no partner takes the whole line rather than
                          // half of it, which is what left "since 2010" stranded
                          // under a truncated publisher.
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

      {/* The expand footer belongs to the ROW only — the prototype's GridCard has
          no footer, and adding one had a consequence beyond the extra control:
          grid rows stretch to their tallest card, so one bundle inflated every
          sibling in its row and their bottom-pinned meta rows drifted away from
          the title. On a tile the thumbnail's count badge already says how many
          layers there are, and the card opens the bundle. */}
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
