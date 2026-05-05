import type { Layer } from "@/lib/validations/layer";
import type { FormatNumberTypes } from "@/lib/validations/common";
import type { MapGeoJSONFeature } from "react-map-gl/maplibre";


export enum EditorModes {
  DRAW = "draw",
  MODIFY_GEOMETRY = "modify_geometry",
  MODIFY_ATTRIBUTES = "modify_attributes",
  DELETE = "delete",
}

export type MapPopoverEditorProps = {
  title?: string;
  lngLat?: [number, number];
  feature?: MapGeoJSONFeature | undefined;
  editMode: EditorModes;
  layer: Layer;
  onClose: () => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onConfirm: (payload: any) => void;
};



export interface MapPopoverInfoProps {
  title: string;
  properties?: Record<string, string>; // Keep properties flexible
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  jsonProperties?: Record<string, Array<{ [key: string]: any }>>; // Allow any value type in data
  lngLat: [number, number];
  /**
   * Optional layer id. When set, the popup applies the layer's
   * per-field formatting (kind + display_config from queryables) to
   * property values whose key matches a known column.
   */
  layerId?: string;
  /**
   * When a field_list interaction is configured, maps column names to
   * display labels and controls which fields are shown (and in what order).
   */
  fieldLabels?: Record<string, string>;
  fieldOrder?: string[];
  /**
   * Per-field prefix/suffix/format overrides from the field_list config.
   * Applied after kind-aware formatting (so area units are preserved).
   */
  fieldDecorators?: Record<string, { prefix?: string; suffix?: string; format?: FormatNumberTypes }>;
  onClose: () => void;
}

