import { useMemo } from "react";

import { createTheme, useTheme } from "@mui/material/styles";

/** Converts a hex color like `#3A3541` to the `"R, G, B"` string used by the palette. */
function hexToRgb(hex: string): string | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return null;
  return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
}

/**
 * Returns a MUI theme with brand overrides applied when set.
 *
 * - `primaryColor` overrides `palette.primary`. Active tab text is pinned to
 *   neutral so only the underline indicator picks up the brand color.
 * - `iconColor` overrides `palette.action.active` — icon buttons only.
 *   Does NOT touch `text.secondary` to keep captions/labels readable.
 * - `fontColor` replaces the base text RGB used to derive the full text and
 *   action palette: `text.{primary,secondary,disabled}`, all `action.*` tokens,
 *   and `divider`. If `iconColor` is also set it takes precedence over
 *   `action.active` regardless of `fontColor`.
 *
 * Falls back to the base theme when none are provided.
 */
export function useBrandedTheme(
  primaryColor: string | undefined,
  iconColor: string | undefined,
  fontColor: string | undefined,
) {
  const baseTheme = useTheme();
  return useMemo(() => {
    if (!primaryColor && !iconColor && !fontColor) return baseTheme;

    const palette: Record<string, unknown> = {};

    if (primaryColor) {
      palette.primary = baseTheme.palette.augmentColor({ color: { main: primaryColor } });
    }

    if (fontColor) {
      const rgb = hexToRgb(fontColor);
      if (rgb) {
        palette.text = {
          primary: `rgba(${rgb}, 0.87)`,
          secondary: `rgba(${rgb}, 0.68)`,
          disabled: `rgba(${rgb}, 0.38)`,
        };
        palette.divider = `rgba(${rgb}, 0.12)`;
        // Build full action palette from font color; iconColor overrides active below.
        palette.action = {
          active: `rgba(${rgb}, 0.70)`,
          hover: `rgba(${rgb}, 0.04)`,
          selected: `rgba(${rgb}, 0.08)`,
          disabled: `rgba(${rgb}, 0.30)`,
          disabledBackground: `rgba(${rgb}, 0.18)`,
          focus: `rgba(${rgb}, 0.12)`,
        };
      }
    }

    // iconColor always wins over the font-color-derived action.active
    if (iconColor) {
      palette.action = {
        ...(palette.action as Record<string, unknown> ?? baseTheme.palette.action),
        active: iconColor,
      };
    }

    const components: Record<string, unknown> = {};
    if (primaryColor) {
      components.MuiTab = {
        styleOverrides: {
          textColorPrimary: {
            "&.Mui-selected": {
              color: baseTheme.palette.text.primary,
            },
          },
        },
      };
    }

    return createTheme(baseTheme, { palette, components });
  }, [baseTheme, primaryColor, iconColor, fontColor]);
}
