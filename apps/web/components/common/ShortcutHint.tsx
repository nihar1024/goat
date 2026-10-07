"use client";

import { Box } from "@mui/material";
import { useEffect, useState } from "react";

import { shortcutLabel } from "@/lib/utils/platform";

interface ShortcutHintProps {
  /** The key pressed together with Ctrl or Command, e.g. `K`. */
  letter: string;
}

/**
 * The key badge shown inside a field that has a Ctrl/Cmd shortcut.
 *
 * The label is decided from the browser, so it reads `⌘K` on a Mac and
 * `Ctrl+K` on Windows and Linux. That can only be known on the client, so
 * nothing is rendered until after mount — the server has no platform to
 * render, and guessing one would mismatch on hydration.
 *
 * Nor is anything shown on a device with no mouse or trackpad (a phone, a
 * tablet without one): it has no keyboard to press the shortcut on.
 */
const ShortcutHint: React.FC<ShortcutHintProps> = ({ letter }) => {
  const [label, setLabel] = useState<string | null>(null);

  useEffect(() => {
    // Without matchMedia (older browsers, tests) the hint is shown, as before.
    const hasPointer =
      typeof window.matchMedia !== "function" || window.matchMedia("(any-pointer: fine)").matches;
    setLabel(hasPointer ? shortcutLabel(letter, window.navigator) : null);
  }, [letter]);

  if (!label) return null;

  return (
    <Box
      component="kbd"
      sx={{
        fontFamily: "inherit",
        fontSize: 11.5,
        color: "text.secondary",
        border: (theme) => `1px solid ${theme.palette.divider}`,
        borderRadius: "5px",
        px: "6px",
        py: "1px",
        whiteSpace: "nowrap",
      }}>
      {label}
    </Box>
  );
};

export default ShortcutHint;
