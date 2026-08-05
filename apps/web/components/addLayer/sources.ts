import { ICON_NAME } from "@p4b/ui/components/Icon";

import { AddLayerSourceType } from "@/types/common";

/**
 * The sources a layer can come from — one tab each in the Add Layer modal.
 *
 * Labels are single words where a single word will do: the modal is already called
 * Add Layer, so "Dataset Upload" and "Dataset Explorer" were repeating its subject
 * back at the reader and costing a 44px tab bar its room.
 *
 * A source either has a flow of its own (a controller + a body) or, until it does,
 * a `handoff` to the dialog that still owns it. Hosts filter the list; nothing else
 * decides which tabs exist.
 */

/**
 * How wide the dialog is on a browsing tab, and the width its body lays out at.
 *
 * Both, from one constant, on purpose: the paper animates towards this while the body
 * is already at it, so the tab is revealed rather than reflowed. Were the body to size
 * itself off the animating paper instead, its cards would be laid out two-up, then
 * three-up, resizing under the cursor for the length of the transition.
 */
export const ADD_LAYER_WIDE_WIDTH = "min(1360px, 94vw)";

export type AddLayerSourceId = "upload" | "explorer" | "catalog" | "connections" | "create";

export type AddLayerSource = {
  id: AddLayerSourceId;
  /** i18n key for the tab label. */
  labelKey: string;
  icon: ICON_NAME;
  /** i18n keys for the steps this source walks through; a single view declares none. */
  stepKeys?: string[];
  /** Adds to a project, so it is absent where there is none (the datasets page). */
  needsProject?: boolean;
  /** Browsing sources need room for a filter rail beside a list of cards. */
  wide?: boolean;
  /** The legacy dialog to open until this source has a flow. */
  handoff?: AddLayerSourceType;
};

export const ADD_LAYER_SOURCES: AddLayerSource[] = [
  {
    id: "upload",
    labelKey: "upload",
    icon: ICON_NAME.UPLOAD,
    // The tabular step appears only for CSV/XLSX — the flow reports the real list.
    stepKeys: ["select_file", "destination_and_metadata", "confirmation"],
  },
  {
    id: "explorer",
    // "My datasets" rather than "Explore": it is the counterpart to Catalog,
    // and what distinguishes the two is whose datasets they are.
    labelKey: "my_datasets",
    icon: ICON_NAME.DATABASE,
    needsProject: true,
    wide: true,
    handoff: AddLayerSourceType.DatasourceExplorer,
  },
  {
    id: "catalog",
    labelKey: "catalog",
    icon: ICON_NAME.GLOBE,
    needsProject: true,
    wide: true,
  },
  {
    id: "connections",
    // "Connections" is the feature; `dataset_external` names only today's stand-in.
    labelKey: "connections",
    icon: ICON_NAME.LINK,
    wide: true,
    handoff: AddLayerSourceType.DataSourceExternal,
  },
  {
    id: "create",
    labelKey: "create_layer",
    icon: ICON_NAME.PLUS,
    // `createEmptyLayer` posts to a project; without one there is nothing to add
    // the new layer to, so the datasets page does not offer it.
    needsProject: true,
  },
];

export const sourcesFor = ({ hasProject }: { hasProject: boolean }): AddLayerSource[] =>
  ADD_LAYER_SOURCES.filter((source) => hasProject || !source.needsProject);
