import { type CatalogKind } from "@/lib/catalog/kind";
import { type CatalogPeriod, datasetPeriod, itemPeriod } from "@/lib/catalog/period";
import type { CatalogCollection, CatalogItem } from "@/lib/validations/catalog";

/**
 * What a result card needs, independent of what it was built from.
 *
 * The catalog has two kinds of row and the same card renders both: the result
 * list shows **datasets** (STAC Collections) and a bundle's detail page shows the
 * **layers** inside one (STAC Items). Giving the card one shape and two adapters
 * is what lets it stay presentational.
 *
 * This replaced a card that took an Item and guessed the rest. Both properties it
 * guessed from — `goat:layerType` and `goat:member_count` — are denormalised from
 * the collection onto every layer, so a layer listed inside its own bundle claimed
 * to *be* that bundle. The fix used to be an `asMember` flag threaded down from
 * whoever knew better; with an explicit model the ambiguity cannot be expressed in
 * the first place.
 */
export type CatalogCardModel = {
  /** Where the card navigates: a collection id for a dataset, an item id for a layer. */
  href: string;
  title: string;
  description?: string;
  kind: CatalogKind;
  /** Layers in this dataset. 1 for a layer, and for a single-layer dataset. */
  memberCount: number;
  /** Set only for a dataset with more than one layer, to list them inline. */
  bundleId?: string;
  thumbnailHref?: string;
  publisher?: string;
  license?: string;
  languageCode?: string;
  /** When the data is from, where the source says. */
  period?: CatalogPeriod;
  /**
   * What shape the data is — `point`, `line` or `polygon`.
   *
   * On a dataset this is its layers' geometry type where they all agree on one
   * (mirror v5 resolves it; 3,167 of 3,834 datasets have one, the rest being
   * genuinely mixed bundles). Undefined is a real answer, and the thumbnail says
   * "geodata of some shape" rather than picking a shape for it.
   */
  geometryType?: string;
};

/**
 * Fields a card deliberately does NOT carry, with the measurement behind each
 * (live bucket, 3,834 datasets):
 *
 * - **`updated`** — the harvest clock, not the data's date (contract C11). 58
 *   distinct values over 3,834 datasets, all inside one harvest window, so every
 *   card printed the same date and it told a reader nothing. It stays on the
 *   detail page, where it is labelled "Last retrieved" and cannot be mistaken
 *   for the data's own date.
 * - **`category`** — published on 4% of datasets, and every one of them says
 *   `other`: one distinct value across the whole catalog.
 * - **`geographical_code`** — 1.9% coverage.
 *
 * Both of the last two return to the card the moment the harvester fills them
 * (C9); the card is not the place to advertise an empty vocabulary.
 */

/**
 * A publicly dereferenceable thumbnail, or `undefined`.
 *
 * The API has already dropped the assets it will not publish, but a relative href
 * would resolve against the web app's own origin and 404, so absolute http(s)
 * only.
 */
const thumbnailHref = (assets: CatalogItem["assets"] | undefined) => {
  const href = assets?.thumbnail?.href;
  if (!href) return undefined;
  return /^https?:\/\//i.test(href) ? href : undefined;
};

/**
 * A dataset card, from the Collection that *is* the dataset.
 *
 * Everything a card shows lives here natively — title, description, keywords,
 * publisher, licence, category, region, extent — because the harvester publishes
 * dataset-level metadata on the collection. Nothing has to be inferred from a
 * representative layer.
 */
export const datasetCard = (collection: CatalogCollection): CatalogCardModel => {
  const memberCount = collection["goat:member_count"] ?? 1;
  const layerType = collection["goat:layerType"];
  return {
    href: `/catalog/${encodeURIComponent(collection.id)}`,
    title: collection.title || collection.id,
    description: collection.description ?? undefined,
    // A dataset of several layers is a bundle whatever its layers are; otherwise
    // its single layer's type is the dataset's type.
    kind:
      memberCount > 1
        ? "bundle"
        : layerType === "raster" || layerType === "table"
          ? layerType
          : layerType === "feature"
            ? "vector"
            : "unknown",
    memberCount,
    bundleId: memberCount > 1 ? collection.id : undefined,
    thumbnailHref: thumbnailHref(collection.assets as CatalogItem["assets"]),
    publisher: collection["goat:publisher"] ?? undefined,
    license: collection.license ?? undefined,
    languageCode: (collection.language as { code?: string } | undefined)?.code,
    period: datasetPeriod(collection),
    geometryType: (collection["goat:geometryType"] as string | null) ?? undefined,
  };
};

/**
 * A layer card, from an Item — used for the members listed inside a bundle.
 *
 * `goat:layerType` is inherited from the collection and therefore says "bundle"
 * for every member, so it is not read here at all. The layer's own fields settle
 * its kind: a geometry type means vector, a row count without geometry means
 * tabular, and neither is reported as unknown rather than guessed.
 */
export const layerCard = (item: CatalogItem): CatalogCardModel => {
  const props = item.properties;
  return {
    href: `/catalog/${encodeURIComponent(item.id)}`,
    title: props.title,
    description: props.description ?? undefined,
    kind: props["goat:geometryType"]
      ? "vector"
      : typeof props["table:row_count"] === "number"
        ? "table"
        : "unknown",
    // A layer is one layer. It never carries its siblings' count into a card.
    memberCount: 1,
    thumbnailHref: thumbnailHref(item.assets),
    publisher: props["goat:publisher"] ?? undefined,
    license: props.license ?? undefined,
    languageCode: props.language?.code ?? undefined,
    period: itemPeriod(item),
    geometryType: props["goat:geometryType"] ?? undefined,
  };
};
