import type { SelectorItem } from "@/types/map/common";

/** A column constrained to a vocabulary, as the field metadata reports it. */
export type VocabularyField = {
  allowed_values?: (string | number)[];
  allow_other?: boolean;
  default_value?: unknown;
};

/** Whether a field should be edited by picking rather than typing. */
export function hasVocabulary(field: VocabularyField): boolean {
  return Array.isArray(field.allowed_values) && field.allowed_values.length > 0;
}

/**
 * The options to offer for a constrained column, given what it holds now.
 *
 * A value already in the data that is outside the vocabulary is included, so
 * editing some other attribute of that feature does not quietly rewrite this
 * one — imported data predates the vocabulary and legitimately holds values it
 * does not contain. Only what the user may newly choose is constrained.
 *
 * An empty option leads when the column has no default, because a constrained
 * column is not thereby a required one and clearing it has to stay possible.
 * With a default it is left out: the value would come straight back — a street
 * network edge's class is refilled on every save, so offering a blank would
 * show the user a choice that silently undoes itself.
 */
export function vocabularyItems(field: VocabularyField, current: unknown): SelectorItem[] {
  const allowed = field.allowed_values ?? [];
  const clearable = field.default_value === undefined || field.default_value === null;
  const items: SelectorItem[] = [
    ...(clearable ? [{ value: "", label: "—" }] : []),
    ...allowed.map((value) => ({ value, label: String(value) })),
  ];
  const isSet = current !== null && current !== undefined && current !== "";
  if (isSet && !allowed.some((value) => String(value) === String(current))) {
    items.push({ value: current as string | number, label: String(current) });
  }
  return items;
}

/** The item matching a stored value, for Selector's controlled `selectedItems`. */
export function selectedVocabularyItem(
  items: SelectorItem[],
  current: unknown
): SelectorItem | undefined {
  if (current === null || current === undefined || current === "") return undefined;
  return items.find((item) => String(item.value) === String(current));
}

/** A field that supplies a value when a new feature leaves it blank. */
export type DefaultedField = { name: string; default_value?: unknown };

/**
 * The properties a newly created feature starts with.
 *
 * Seeded in the editor rather than left to the server so the user sees the
 * value that will be stored. The write path applies the same defaults, so an
 * API caller gets them too — this only decides what is on screen.
 */
export function defaultProperties(fields: DefaultedField[]): Record<string, unknown> {
  const seeded: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.default_value !== undefined && field.default_value !== null) {
      seeded[field.name] = field.default_value;
    }
  }
  return seeded;
}
