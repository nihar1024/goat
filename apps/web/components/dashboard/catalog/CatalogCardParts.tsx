import { Box, Stack, Typography, useTheme } from "@mui/material";
import type { SxProps, Theme } from "@mui/material";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

/** Card primitives: the type tag overlaid on a thumbnail, and one cell of the meta grid. */

/** `TypeTag` — the kind, overlaid on the thumbnail's top-left corner. */
export const TypeTag = ({ label, locked }: { label: string; locked?: boolean }) => (
  <Box
    sx={{
      display: "inline-flex",
      alignItems: "center",
      gap: 1,
      height: 20,
      px: 2.5,
      borderRadius: "6px",
      // A fixed neutral, not a theme colour: it sits on the generated map
      // thumbnail, where a themed surface would disappear into the mint.
      backgroundColor: "#74707A",
      backdropFilter: "blur(2px)",
      fontSize: 12,
      fontWeight: 600,
      letterSpacing: 0.2,
      color: "#fff",
      whiteSpace: "nowrap",
    }}>
    {locked && <Icon iconName={ICON_NAME.LOCK} style={{ fontSize: 10 }} htmlColor="#fff" />}
    {label}
  </Box>
);

/** `Meta` — one labelled cell of a card's meta grid. */
export const Meta = ({
  icon,
  label,
  sx,
}: {
  icon: ICON_NAME;
  label: string;
  sx?: SxProps<Theme>;
}) => {
  const theme = useTheme();
  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="center"
      title={label}
      sx={{ minWidth: 0, ...sx }}>
      <Icon
        iconName={icon}
        style={{ fontSize: 12 }}
        htmlColor={theme.palette.text.secondary}
      />
      <Typography variant="caption" color="text.secondary" noWrap sx={{ minWidth: 0 }}>
        {label}
      </Typography>
    </Stack>
  );
};
