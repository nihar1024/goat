import { Box, Button, FormControl, Link, MenuItem, Select, Stack, Switch, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { BASEMAPS } from "@/lib/constants/basemaps";

import WidgetColorPicker from "@/components/builder/widgets/common/WidgetColorPicker";

import { languages } from "@/i18n/settings";

import type { InteractionRule } from "@/lib/validations/interaction";
import type { BuilderPanelSchema, ControlKey, ControlPositions, Project, ProjectLayer, ProjectLayerGroup } from "@/lib/validations/project";
import { DEFAULT_CONTROL_POSITIONS, DEFAULT_FAVICON_URL, builderConfigSchema } from "@/lib/validations/project";

import InteractionsModal, { InteractionsEntryButton } from "@/components/builder/InteractionsModal";
import MapControlsLayout from "@/components/builder/MapControlsLayout";
import SettingsGroupHeader from "@/components/builder/widgets/common/SettingsGroupHeader";
import Selector from "@/components/map/panels/common/Selector";
import MarkerIconPicker from "@/components/map/panels/style/marker/MarkerIconPicker";

/** Google Fonts available for dashboard display */
const DASHBOARD_FONTS = [
  { label: "Mulish", value: "Mulish, sans-serif" },
  { label: "Roboto", value: "Roboto, sans-serif" },
  { label: "Open Sans", value: "'Open Sans', sans-serif" },
  { label: "Lato", value: "Lato, sans-serif" },
  { label: "Inter", value: "Inter, sans-serif" },
  { label: "Poppins", value: "Poppins, sans-serif" },
  { label: "Montserrat", value: "Montserrat, sans-serif" },
  { label: "Nunito", value: "Nunito, sans-serif" },
  { label: "Source Sans 3", value: "'Source Sans 3', sans-serif" },
  { label: "Raleway", value: "Raleway, sans-serif" },
  { label: "PT Sans", value: "'PT Sans', sans-serif" },
  { label: "Merriweather", value: "Merriweather, serif" },
  { label: "Playfair Display", value: "'Playfair Display', serif" },
  { label: "Lora", value: "Lora, serif" },
];

const GOAT_GREEN = "#2BB381";
const DEFAULT_ICON_COLOR = "#8A8D93";
const DEFAULT_FONT_COLOR = "#3A3541";

interface SettingsTabProps {
  settings: { [key: string]: unknown };
  onChange: (name: string, value: unknown) => void;
  onReset: () => void;
  project?: Project;
  projectLayers?: ProjectLayer[];
  projectLayerGroups?: ProjectLayerGroup[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onProjectUpdate?: (key: string, value: any, refresh?: boolean) => void;
}

const SettingsTab: React.FC<SettingsTabProps> = ({
  settings,
  onChange,
  onReset,
  project,
  projectLayers = [],
  projectLayerGroups = [],
  onProjectUpdate,
}) => {
  const { t } = useTranslation("common");

  // Load all Google Fonts for dropdown preview
  useEffect(() => {
    const id = "dashboard-font-preview";
    if (document.getElementById(id)) return;
    const families = DASHBOARD_FONTS.map((f) => `family=${encodeURIComponent(f.label)}:wght@400;700`).join("&");
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?${families}&display=swap`;
    document.head.appendChild(link);
  }, []);

  const [showInteractionsModal, setShowInteractionsModal] = useState(false);

  const builderConfig = useMemo(() => {
    const parsed = builderConfigSchema.safeParse(project?.builder_config);
    return parsed.success ? parsed.data : undefined;
  }, [project]);

  const interactions = useMemo(
    () => (builderConfig?.interactions ?? []) as InteractionRule[],
    [builderConfig]
  );

  const panels = useMemo(
    () => (builderConfig?.interface ?? []) as BuilderPanelSchema[],
    [builderConfig]
  );

  const handleInteractionsChange = (newInteractions: InteractionRule[]) => {
    if (!builderConfig) return;
    const updatedConfig = { ...builderConfig, interactions: newInteractions };
    onProjectUpdate?.("builder_config", updatedConfig);
  };

  return (
    <Stack direction="column" spacing={2} justifyContent="space-between" sx={{ p: 3 }}>
      <Stack direction="column">
        {/* ── Map ── */}
        <Box sx={{ mb: 6 }}>
          <SettingsGroupHeader label={t("map")} />
          <Stack spacing={2}>
            {/* Toolbar / Scalebar toggles */}
            <Stack direction="row" alignItems="center">
              <Switch
                size="small"
                name="toolbar"
                checked={(settings?.toolbar as boolean) ?? true}
                onChange={(e) => onChange("toolbar", e.target.checked)}
              />
              <Typography variant="body2" color="textSecondary">
                {t("toolbar")}
              </Typography>
            </Stack>
            <Stack direction="row" alignItems="center">
              <Switch
                size="small"
                name="scalebar"
                checked={(settings?.scalebar as boolean) ?? true}
                onChange={(e) => onChange("scalebar", e.target.checked)}
              />
              <Typography variant="body2" color="textSecondary">
                {t("scalebar")}
              </Typography>
            </Stack>

            {/* Control layout picker */}
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
                {t("control_layout")}
              </Typography>
              <MapControlsLayout
                controlPositions={(settings?.control_positions as ControlPositions) ?? DEFAULT_CONTROL_POSITIONS}
                onChange={(positions) => onChange("control_positions", positions)}
              />
            </Box>

            {/* Basemap allowlist — only shown when basemap control is placed in any corner */}
            {Object.values((settings?.control_positions as ControlPositions) ?? {}).some((arr) => (arr as ControlKey[]).includes("basemap")) && (
              <Box>
                <Selector
                  multiple
                  label={t("allowed_basemaps")}
                  placeholder={t("basemaps")}
                  items={BASEMAPS.map((b) => ({ value: b.value, label: b.title }))}
                  selectedItems={
                    (settings?.allowed_basemaps as string[] | null) === null
                      ? BASEMAPS.map((b) => ({ value: b.value, label: b.title }))
                      : BASEMAPS.filter((b) =>
                          (settings?.allowed_basemaps as string[]).includes(b.value)
                        ).map((b) => ({ value: b.value, label: b.title }))
                  }
                  setSelectedItems={(items) => {
                    const selected = (items as { value: string; label: string }[] ?? []).map((i) => i.value);
                    onChange(
                      "allowed_basemaps",
                      selected.length === BASEMAPS.length ? null : selected
                    );
                  }}
                />
              </Box>
            )}
          </Stack>
        </Box>
        <Box sx={{ mb: 6 }}>
          <SettingsGroupHeader label={t("branding")} />
          <Stack spacing={2}>
            {/* Font */}
            <FormControl size="small" fullWidth>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
                {t("font")}
              </Typography>
              <Select
                value={(settings?.font_family as string) || "Mulish, sans-serif"}
                onChange={(e) => onChange("font_family", e.target.value)}
                renderValue={(selected) => {
                  const font = DASHBOARD_FONTS.find((f) => f.value === selected);
                  return font?.label ?? "Mulish";
                }}>
                {DASHBOARD_FONTS.map((font) => (
                  <MenuItem key={font.value} value={font.value}>
                    <Typography sx={{ fontFamily: font.value }}>{font.label}</Typography>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Primary Color */}
            <Box>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("primary_color")}
                </Typography>
                {!!settings?.primary_color && (
                  <Link
                    component="button"
                    variant="caption"
                    underline="always"
                    onClick={() => onChange("primary_color", undefined)}
                    sx={{ cursor: "pointer" }}>
                    {t("reset")}
                  </Link>
                )}
              </Stack>
              <WidgetColorPicker
                color={(settings?.primary_color as string) || GOAT_GREEN}
                onChange={(color) => onChange("primary_color", color)}
              />
            </Box>

            {/* Icon Color */}
            <Box>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("icon_color")}
                </Typography>
                {!!settings?.icon_color && (
                  <Link
                    component="button"
                    variant="caption"
                    underline="always"
                    onClick={() => onChange("icon_color", undefined)}
                    sx={{ cursor: "pointer" }}>
                    {t("reset")}
                  </Link>
                )}
              </Stack>
              <WidgetColorPicker
                color={(settings?.icon_color as string) || DEFAULT_ICON_COLOR}
                onChange={(color) => onChange("icon_color", color)}
              />
            </Box>

            {/* Font Color */}
            <Box>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
                <Typography variant="caption" color="text.secondary">
                  {t("font_color")}
                </Typography>
                {!!settings?.font_color && (
                  <Link
                    component="button"
                    variant="caption"
                    underline="always"
                    onClick={() => onChange("font_color", undefined)}
                    sx={{ cursor: "pointer" }}>
                    {t("reset")}
                  </Link>
                )}
              </Stack>
              <WidgetColorPicker
                color={(settings?.font_color as string) || DEFAULT_FONT_COLOR}
                onChange={(color) => onChange("font_color", color)}
              />
            </Box>

            {/* Favicon */}
            <MarkerIconPicker
              label={t("favicon")}
              selectedMarker={
                settings?.favicon_url
                  ? {
                      name: (settings.favicon_url as string) === DEFAULT_FAVICON_URL ? "GOAT" : t("favicon"),
                      url: settings.favicon_url as string,
                      category: "",
                      source: "custom",
                    }
                  : undefined
              }
              onSelectMarker={(marker) => {
                onChange("favicon_url", marker.url || DEFAULT_FAVICON_URL);
              }}
            />

          </Stack>
        </Box>
        {/* ── General ── */}
        <Box sx={{ mb: 6 }}>
          <SettingsGroupHeader label={t("general")} />
          <Stack spacing={2}>
            <FormControl size="small" fullWidth>
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
                {t("language")}
              </Typography>
              <Select
                value={(settings?.language as string) ?? "auto"}
                onChange={(e) => onChange("language", e.target.value)}>
                <MenuItem value="auto">{t("auto_browser_default")}</MenuItem>
                {languages.map((lng) => (
                  <MenuItem key={lng} value={lng}>
                    {lng === "en" ? "English" : lng === "de" ? "Deutsch" : lng}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>
        </Box>
        {project && onProjectUpdate && (
          <Box sx={{ mb: 6 }}>
            <SettingsGroupHeader label={t("interactions")} />
            <InteractionsEntryButton
              interactionCount={interactions.filter((r) => r.enabled).length}
              onClick={() => setShowInteractionsModal(true)}
            />
          </Box>
        )}
      </Stack>
      <Stack>
        <Button onClick={onReset} fullWidth size="small" color="error">
          <Typography variant="body2" fontWeight="bold" color="inherit">
            {t("common:reset")}
          </Typography>
        </Button>
      </Stack>
      {showInteractionsModal && builderConfig && (
        <InteractionsModal
          open={showInteractionsModal}
          onClose={() => setShowInteractionsModal(false)}
          interactions={interactions}
          onChange={handleInteractionsChange}
          panels={panels}
          projectLayers={projectLayers}
          projectLayerGroups={projectLayerGroups}
        />
      )}
    </Stack>
  );
};

export default SettingsTab;
