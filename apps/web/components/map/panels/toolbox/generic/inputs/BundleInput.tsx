/**
 * Generic Bundle Input Component
 *
 * Renders a bundle selector based on an OGC process input schema
 * (x-ui.widget === "bundle-selector"). Lists bundles the user can access,
 * optionally restricted to those with a ready artifact of a given kind
 * (widget_options.artifact_kind, e.g. "pt_network_graph"). The selected
 * bundle's UUID is stored directly as the field value.
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { ICON_NAME } from "@p4b/ui/components/Icon";

import type { SelectorItem } from "@/types/map/common";
import type { ProcessedInput } from "@/types/map/ogc-processes";

import { useBundles } from "@/lib/api/bundles";

import Selector from "@/components/map/panels/common/Selector";

interface BundleInputProps {
  input: ProcessedInput;
  value: string | undefined;
  onChange: (value: string | undefined) => void;
  disabled?: boolean;
}

export default function BundleInput({ input, value, onChange, disabled }: BundleInputProps) {
  const { t } = useTranslation("common");

  const opts = input.uiMeta?.widget_options ?? {};
  const { data: bundles } = useBundles({
    bundleType: opts.bundle_type as string | undefined,
    artifactKind: opts.artifact_kind as string | undefined,
  });

  const bundleItems: SelectorItem[] = useMemo(
    () => (bundles ?? []).map((bundle) => ({ value: bundle.id, label: bundle.name })),
    [bundles]
  );

  const selectedItem = useMemo(
    () => (value ? bundleItems.find((item) => item.value === value) : undefined),
    [value, bundleItems]
  );

  const handleChange = (item: SelectorItem | SelectorItem[] | undefined) => {
    const selected = Array.isArray(item) ? item[0] : item;
    onChange(selected?.value as string | undefined);
  };

  const label = input.uiMeta?.label || input.title;
  const tooltip = input.uiMeta?.description || input.description || "";

  return (
    <Selector
      selectedItems={selectedItem}
      setSelectedItems={handleChange}
      items={bundleItems}
      label={label}
      tooltip={tooltip}
      placeholder={t("select_bundle")}
      emptyMessage={t("no_bundles_found")}
      emptyMessageIcon={ICON_NAME.CUBE}
      disabled={disabled}
    />
  );
}
