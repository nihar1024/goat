---
sidebar_position: 3
---

# Settings

In the Settings section, **you can configure the map controls, branding, social sharing, and interaction behaviour of your dashboard**. When you disable a functionality, it will not be available in Viewer mode.

<div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
  <img src={require('/img/builder/interface_settings.webp').default} alt="Dashboard Settings in GOAT" style={{ maxHeight: "auto", maxWidth: "auto", objectFit: "cover"}}/>
</div>

## Map

- `Toolbar` — shows the top bar with the GOAT logo, project name, last saved timestamp, and project info in Viewer mode.
- `Scalebar` — shows a scale on the map for measuring distances from one point to another.

### Control layout

Controls the position of map controls in Viewer mode. Each position (Top-left, Top-right, Bottom-right) can be expanded to add or remove controls as needed.

### Allowed basemaps

Restrict which basemaps viewers can switch to. Select one or more basemaps from the dropdown — viewers will only see the ones you enable here.

---

## Branding

Customize the visual identity of your dashboard for Viewer mode.

- `Font` — select a typeface from the dropdown. Choose `Custom...` to enter a **Font file URL** and **Font Family** name for a custom typeface.

- `Primary Color` — set the main accent color used for buttons and highlights.
- `Icon Color` — set the color for icons throughout the dashboard.
- `Font Color` — set the text color used across the dashboard.
- `Favicon` — upload a custom browser tab icon. Click `×` to remove it.

---

## Social sharing

Customize how your dashboard appears when shared via social media or messaging apps.

- **Preview image** — drag and drop or click to upload an image.
- **Description** — add a short description used in social previews and search results.

---

## General

- `Language` — set the dashboard display language. Options: `Auto (Browser Default)`, `English`, `Deutsch`.

---

## Interactions

Click `Manage Interactions` to open the interactions editor. Interactions link dashboard elements together — for example, clicking a layer group can switch the active tab in a widget. Click `Add Interaction` to create a new one.

---

::::note

Use `Reset` at the bottom of the panel to restore all settings to their defaults.

::::
