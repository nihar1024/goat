"use client";

import { Box, Skeleton, Stack, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

import { useCatalogCollectionItems } from "@/lib/api/catalog";
import type { CatalogItem } from "@/lib/validations/catalog";

import { useCatalogLabels } from "@/hooks/catalog/useCatalogLabels";

/** The layers inside a dataset, listed under its card. */

/** The glyph for a layer, from its own geometry. */
const memberIcon = (item: CatalogItem): ICON_NAME => {
  switch (item.properties["goat:geometryType"]) {
    case "point":
      return ICON_NAME.POINT_FEATURE;
    case "line":
      return ICON_NAME.LINE_FEATURE;
    case "polygon":
      return ICON_NAME.POLYGON_FEATURE;
    default:
      return typeof item.properties["table:row_count"] === "number"
        ? ICON_NAME.TABLE
        : ICON_NAME.LAYERS;
  }
};

const CatalogBundleMembers = ({
  collectionId,
  onOpenMember,
}: {
  collectionId: string;
  onOpenMember?: (memberId: string) => void;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();
  const labels = useCatalogLabels();
  const { items, isLoading, isError } = useCatalogCollectionItems(collectionId, {
    limit: 50,
  });

  if (isLoading) {
    return (
      <Stack spacing={1} sx={{ px: 5, py: 3 }}>
        <Skeleton variant="text" width="60%" />
        <Skeleton variant="text" width="45%" />
      </Stack>
    );
  }

  if (isError || items.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 5, py: 3 }}>
        {t("catalog_bundle_members_unavailable")}
      </Typography>
    );
  }

  return (
    <Stack divider={<Box sx={{ borderTop: `1px solid ${theme.palette.divider}` }} />}>
      {items.map((member) => {
        const rows = member.properties["table:row_count"];
        return (
          <Box
            key={member.id}
            onClick={(event) => {
              // The card behind this row navigates to the dataset; a member row
              // must open the member instead.
              event.stopPropagation();
              onOpenMember?.(member.id);
            }}
            sx={{
              display: "grid",
              // Fixed tracks, right-aligned: ragged `flex` columns put each row's geometry and count at a different x, so the numbers could not be read down the list.
              gridTemplateColumns: "16px minmax(0, 1fr) 88px 96px",
              alignItems: "center",
              columnGap: 3,
              px: 5,
              py: 2.5,
              cursor: onOpenMember ? "pointer" : "default",
              "&:hover": onOpenMember
                ? { backgroundColor: theme.palette.action.hover }
                : undefined,
            }}>
            <Icon
              iconName={memberIcon(member)}
              style={{ fontSize: 13 }}
              htmlColor={theme.palette.text.secondary}
            />
            <Typography variant="body2" noWrap title={member.properties.title}>
              {member.properties.title}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {labels.geometryLabel(member.properties["goat:geometryType"])}
            </Typography>
            <Typography variant="caption" color="text.secondary" align="right" noWrap>
              {typeof rows === "number" ? t("catalog_row_count_short", { count: rows }) : ""}
            </Typography>
          </Box>
        );
      })}
    </Stack>
  );
};

export default CatalogBundleMembers;
