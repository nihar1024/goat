import { Box, useTheme } from "@mui/material";
import { useState } from "react";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import type { CatalogKind } from "@/lib/catalog/kind";

/** A card's picture: the dataset's own thumbnail when one is published, and a drawn stand-in when not. */

/** Which mark, from the most specific thing the card knows. */
const markFor = (kind: CatalogKind, geometryType?: string): ICON_NAME => {
  if (kind === "table") return ICON_NAME.TABLE;
  if (kind === "raster") return ICON_NAME.IMAGE;
  switch (geometryType) {
    case "point":
      return ICON_NAME.POINT_FEATURE;
    case "line":
      return ICON_NAME.LINE_FEATURE;
    case "polygon":
      return ICON_NAME.POLYGON_FEATURE;
    default:
      return ICON_NAME.LAYERS;
  }
};

type Texture = "dots" | "raked" | "mesh" | "rules" | "pixels" | "graticule";

const textureFor = (kind: CatalogKind, geometryType?: string): Texture => {
  if (kind === "table") return "rules";
  if (kind === "raster") return "pixels";
  switch (geometryType) {
    case "point":
      return "dots";
    case "line":
      return "raked";
    case "polygon":
      return "mesh";
    default:
      return "graticule";
  }
};

/** The ground pattern, as CSS gradients rather than an image or an SVG defs block: a tile is 44–200px wide and there can be 24 of them on screen, so the pattern has to cost nothing to paint and stay crisp at every size. */
const textureCss = (texture: Texture, line: string): string => {
  switch (texture) {
    case "dots":
      return `radial-gradient(${line} 1.4px, transparent 1.5px)`;
    case "raked":
      return `repeating-linear-gradient(28deg, ${line} 0 1.5px, transparent 1.5px 13px)`;
    case "mesh":
      return (
        `repeating-linear-gradient(60deg, ${line} 0 1.5px, transparent 1.5px 16px),` +
        `repeating-linear-gradient(-60deg, ${line} 0 1.5px, transparent 1.5px 16px)`
      );
    case "rules":
      return `repeating-linear-gradient(to bottom, ${line} 0 1.5px, transparent 1.5px 12px)`;
    case "pixels":
      return (
        `repeating-linear-gradient(to right, ${line} 0 1px, transparent 1px 10px),` +
        `repeating-linear-gradient(to bottom, ${line} 0 1px, transparent 1px 10px)`
      );
    case "graticule":
      return (
        `linear-gradient(to right, ${line} 1px, transparent 1px),` +
        `linear-gradient(to bottom, ${line} 1px, transparent 1px)`
      );
  }
};

const textureSize = (texture: Texture): string | undefined => {
  if (texture === "dots") return "11px 11px";
  if (texture === "pixels") return "10px 10px";
  if (texture === "graticule") return "14px 14px";
  return undefined;
};

type Props = {
  kind: CatalogKind;
  /** The data's shape, where the dataset states one. */
  geometryType?: string;
  /** `grid` is a 16:9 band above the title, `list` a tile beside it, and `mark` a small square for a phone — where a full-width band is 200px of decoration that pushes the next dataset off the screen. */
  variant?: "grid" | "list" | "mark";
  /** Shown as a badge on a bundle. */
  memberCount?: number;
  href?: string;
};

const CatalogThumbnail = ({
  kind,
  geometryType,
  variant = "grid",
  memberCount,
  href,
}: Props) => {
  const theme = useTheme();
  const [failed, setFailed] = useState(false);
  const dark = theme.palette.mode === "dark";

  // Cool neutrals, a step away from the card's own surface so the tile reads as
  // a picture rather than as a hole in the card.
  const ground = dark ? "#1B2532" : "#EEF2F6";
  const accent = dark ? "#8FB4D4" : "#4A7396";
  const pattern = dark ? "rgba(143, 180, 212, 0.20)" : "rgba(74, 115, 150, 0.24)";

  const frame = {
    position: "relative",
    flexShrink: 0,
    overflow: "hidden",
    borderRadius: 2,
    // A list row gives the thumb a 200px column at 130px tall.
    ...(variant === "grid"
      ? { width: "100%", aspectRatio: "16 / 9" }
      : variant === "mark"
        ? { width: 44, height: 44 }
        : { width: 200, height: 130 }),
  } as const;

  if (href && !failed) {
    return (
      <Box sx={frame}>
        <Box
          component="img"
          src={href}
          alt=""
          loading="lazy"
          // A dead thumbnail falls back to the stand-in rather than leaving a
          // broken-image glyph in the grid.
          onError={() => setFailed(true)}
          sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
        />
      </Box>
    );
  }

  const texture = textureFor(kind, geometryType);

  return (
    <Box
      sx={{
        ...frame,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: ground,
      }}
      aria-hidden>
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          backgroundImage: textureCss(texture, pattern),
          backgroundSize: textureSize(texture),
          // Centred so the pattern is symmetrical in the frame whatever the tile's size — a graticule cropped hard on one edge looks like a rendering mistake.
          backgroundPosition: "center",
        }}
      />
      <Icon
        iconName={markFor(kind, geometryType)}
        style={{
          fontSize: variant === "mark" ? 17 : 30,
          // Above the texture, and given a little air so the pattern does not
          // read as part of the glyph.
          position: "relative",
          filter: dark
            ? "drop-shadow(0 0 6px rgba(27, 37, 50, 0.9))"
            : "drop-shadow(0 0 6px rgba(238, 242, 246, 0.95))",
        }}
        htmlColor={accent}
      />
      {/* No count badge on a 44px mark — the card's own footer says how many. */}
      {kind === "bundle" && !!memberCount && variant !== "mark" && (
        <Box
          sx={{
            position: "absolute",
            // Top-right on a row, bottom-right on a tile, where the save control does not sit.
            ...(variant === "grid" ? { bottom: 8 } : { top: 8 }),
            right: 8,
            minWidth: 24,
            height: 24,
            px: 1,
            borderRadius: "999px",
            // A neutral scrim, not the brand's dark green: the chip states a
            // number, it is not something to act on.
            backgroundColor: dark ? "rgba(10, 18, 26, 0.66)" : "rgba(16, 26, 36, 0.52)",
            color: theme.palette.common.white,
            fontSize: 12,
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}>
          {memberCount}
        </Box>
      )}
    </Box>
  );
};

export default CatalogThumbnail;
