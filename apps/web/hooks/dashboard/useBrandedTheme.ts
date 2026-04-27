import { useMemo } from "react";

import { createTheme, useTheme } from "@mui/material/styles";

/**
 * Returns a MUI theme with primary and/or icon color overridden when set.
 * - `primaryColor` overrides `palette.primary` (cascades to buttons, accents, links,
 *   tab indicators). Active tab text is pinned to neutral so only the indicator
 *   reflects the brand color.
 * - `iconColor` overrides `palette.action.active` (cascades to MUI default
 *   IconButton color, three-dot menus, chevrons, and any component that
 *   explicitly references `theme.palette.action.active`). It deliberately does
 *   NOT override `palette.text.secondary` — that token is used for real text
 *   (captions, descriptions, helper text) and must stay readable.
 *
 * Falls back to the base theme when neither is provided.
 */
export function useBrandedTheme(primaryColor: string | undefined, iconColor: string | undefined) {
  const baseTheme = useTheme();
  return useMemo(() => {
    if (!primaryColor && !iconColor) return baseTheme;

    const palette: Record<string, unknown> = {};
    if (primaryColor) {
      palette.primary = baseTheme.palette.augmentColor({ color: { main: primaryColor } });
    }
    if (iconColor) {
      palette.action = { ...baseTheme.palette.action, active: iconColor };
    }

    const components: Record<string, unknown> = {};
    if (primaryColor) {
      // MUI Tabs default to textColor="primary"; the selected text would otherwise
      // pick up the brand color. Pin it to neutral so only the underline indicator
      // reflects the brand. Specificity must match `.MuiTab-textColorPrimary.Mui-selected`.
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
  }, [baseTheme, primaryColor, iconColor]);
}
