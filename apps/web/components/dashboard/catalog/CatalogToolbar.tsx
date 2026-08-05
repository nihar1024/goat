"use client";

import CheckIcon from "@mui/icons-material/Check";
import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";
import GridViewIcon from "@mui/icons-material/GridView";
import SortIcon from "@mui/icons-material/Sort";
import {
  Box,
  IconButton,
  InputBase,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME, Icon } from "@p4b/ui/components/Icon";

/** The catalog's toolbar: a search field, a Grid/List toggle, and a sort dropdown. */

export type CatalogSortOption = { value: string; label: string; icon?: ICON_NAME };

const CatalogToolbar = ({
  q,
  onChangeQ,
  view,
  onChangeView,
  sort,
  sortOptions,
  onChangeSort,
  onOpenFilters,
  activeFilterCount = 0,
  compact,
}: {
  q: string;
  /** Called on every keystroke; the page decides how to debounce. */
  onChangeQ: (value: string) => void;
  view: "list" | "grid";
  onChangeView: (view: "list" | "grid") => void;
  sort: string;
  sortOptions: CatalogSortOption[];
  onChangeSort: (value: string) => void;
  /**
   * Opens the filter drawer. Passed only where the sidebar is not on screen —
   * below `md` — so the control appears exactly when it is the only way in.
   */
  onOpenFilters?: () => void;
  activeFilterCount?: number;
  /** Phone layout: search collapses to an icon that expands over the row, sort loses its label, and the Grid/List toggle is dropped — one column is the only layout a phone has, so the two views render identically there. */
  compact?: boolean;
}) => {
  const { t } = useTranslation("common");
  const theme = useTheme();

  // Local so typing is immediate while the query is debounced, and resynced when
  // the URL changes from elsewhere (Clear all, or a pasted link).
  const [value, setValue] = useState(q);
  useEffect(() => setValue(q), [q]);

  const sortAnchor = useRef<HTMLButtonElement | null>(null);
  const [sortOpen, setSortOpen] = useState(false);
  /** On a phone the field starts collapsed unless it already holds a query. */
  const [searchOpen, setSearchOpen] = useState(!!q);
  const current = sortOptions.find((option) => option.value === sort) ?? sortOptions[0];

  const segment = (id: "grid" | "list", label: string, glyph: React.ReactNode) => {
    const selected = view === id;
    return (
      <Box
        component="button"
        type="button"
        onClick={() => onChangeView(id)}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 1.5,
          height: 32,
          px: 3.25,
          borderRadius: "999px",
          border: "none",
          cursor: "pointer",
          font: "inherit",
          fontSize: 13.5,
          fontWeight: 600,
          color: selected ? theme.palette.primary.main : theme.palette.text.secondary,
          backgroundColor: selected ? theme.palette.action.selected : "transparent",
          transition: theme.transitions.create(["background-color", "color"], { duration: 120 }),
        }}>
        {glyph}
        {label}
      </Box>
    );
  };

  return (
    <Stack direction="row" alignItems="center" useFlexGap flexWrap="wrap" gap={2.5}>
      {compact && !searchOpen ? (
        <IconButton
          aria-label={t("search_datasets")}
          onClick={() => setSearchOpen(true)}
          sx={{
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper,
          }}>
          <Icon
            iconName={ICON_NAME.SEARCH}
            style={{ fontSize: 15 }}
            htmlColor={theme.palette.text.secondary}
          />
        </IconButton>
      ) : (
      <Paper
        elevation={0}
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 2.5,
          flex: "1 1 220px",
          minWidth: 0,
          px: 4,
          py: 2.5,
          borderRadius: "999px",
          border: `1px solid ${theme.palette.divider}`,
          boxShadow: theme.shadows[6],
        }}>
        <Icon
          iconName={ICON_NAME.SEARCH}
          style={{ fontSize: 15 }}
          htmlColor={theme.palette.text.secondary}
        />
        <InputBase
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            onChangeQ(event.target.value);
          }}
          placeholder={t("search_datasets")}
          sx={{ flex: 1, fontSize: 14 }}
        />
        {(value || compact) && (
          <IconButton
            size="small"
            aria-label={t("clear")}
            onClick={() => {
              setValue("");
              onChangeQ("");
              if (compact) setSearchOpen(false);
            }}>
            <Icon
              iconName={ICON_NAME.XCLOSE}
              style={{ fontSize: 12 }}
              htmlColor={theme.palette.text.secondary}
            />
          </IconButton>
        )}
      </Paper>
      )}

      {onOpenFilters && (
        <Box
          component="button"
          type="button"
          onClick={onOpenFilters}
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 1.75,
            height: 38,
            px: 3.25,
            flexShrink: 0,
            borderRadius: "999px",
            cursor: "pointer",
            font: "inherit",
            fontSize: 13.5,
            fontWeight: 600,
            backgroundColor: theme.palette.background.paper,
            border: `1px solid ${
              activeFilterCount ? theme.palette.primary.main : theme.palette.divider
            }`,
            color: activeFilterCount
              ? theme.palette.primary.main
              : theme.palette.text.secondary,
          }}>
          <Icon iconName={ICON_NAME.FILTER} style={{ fontSize: 14 }} htmlColor="currentColor" />
          {t("filter")}
          {activeFilterCount > 0 && (
            <Typography
              component="span"
              sx={{
                fontSize: 11,
                fontWeight: 700,
                px: 1.5,
                borderRadius: "999px",
                backgroundColor: theme.palette.action.selected,
                color: theme.palette.primary.main,
              }}>
              {activeFilterCount}
            </Typography>
          )}
        </Box>
      )}

      {!compact && (
        <Stack
          direction="row"
          spacing={0.5}
          sx={{
            p: "3px",
            flexShrink: 0,
            borderRadius: "999px",
            border: `1px solid ${theme.palette.divider}`,
            backgroundColor: theme.palette.background.paper,
          }}>
          {segment("grid", t("grid"), <GridViewIcon sx={{ fontSize: 15 }} />)}
          {segment("list", t("list"), <FormatListBulletedIcon sx={{ fontSize: 15 }} />)}
        </Stack>
      )}

      <Box
        component="button"
        type="button"
        ref={sortAnchor}
        onClick={() => setSortOpen(true)}
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 1.75,
          height: 38,
          px: compact ? 2.5 : 3.25,
          flexShrink: 0,
          borderRadius: "999px",
          cursor: "pointer",
          font: "inherit",
          fontSize: 13.5,
          fontWeight: 600,
          whiteSpace: "nowrap",
          backgroundColor: theme.palette.background.paper,
          border: `1px solid ${sortOpen ? theme.palette.primary.main : theme.palette.divider}`,
          color: sortOpen ? theme.palette.primary.main : theme.palette.text.secondary,
          transition: theme.transitions.create(["border-color", "color"], { duration: 120 }),
          "&:hover": {
            borderColor: theme.palette.primary.main,
            color: theme.palette.primary.main,
          },
        }}>
        <SortIcon sx={{ fontSize: 16 }} />
        {!compact && current?.label}
        {!compact && (
          <Icon
            iconName={ICON_NAME.CHEVRON_DOWN}
            style={{ fontSize: 11 }}
            htmlColor="currentColor"
          />
        )}
      </Box>
      <Menu
        anchorEl={sortAnchor.current}
        open={sortOpen}
        onClose={() => setSortOpen(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{ paper: { sx: { minWidth: 180, mt: 1.5 } } }}>
        {sortOptions.map((option) => {
          const selected = option.value === sort;
          return (
            <MenuItem
              key={option.value}
              selected={selected}
              onClick={() => {
                onChangeSort(option.value);
                setSortOpen(false);
              }}>
              <Stack direction="row" alignItems="center" spacing={2.5} sx={{ width: "100%" }}>
                {option.icon && (
                  <Icon
                    iconName={option.icon}
                    style={{ fontSize: 13 }}
                    htmlColor={
                      selected ? theme.palette.primary.main : theme.palette.text.secondary
                    }
                  />
                )}
                <Typography
                  variant="body2"
                  sx={{ flex: 1, fontWeight: selected ? 600 : 500 }}
                  color={selected ? "primary" : "text.primary"}>
                  {option.label}
                </Typography>
                {selected && <CheckIcon sx={{ fontSize: 14 }} color="primary" />}
              </Stack>
            </MenuItem>
          );
        })}
      </Menu>
    </Stack>
  );
};

export default CatalogToolbar;
