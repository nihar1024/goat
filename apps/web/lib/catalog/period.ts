/**
 * When a catalog row's data is from.
 *
 * Separate from the label helpers because this is a question about the *data*,
 * not about wording: STAC allows a row to state its time in three places, and
 * every surface that shows a date has to read all three or it shows nothing for
 * the datasets that say the most.
 */

import type { CatalogCollection, CatalogItem } from "@/lib/validations/catalog";

/**
 * A temporal extent, however the row happened to state it. Both bounds are
 * optional: an open-ended dataset ("everything since 2020") publishes one.
 */
export type CatalogPeriod = { start?: string | null; end?: string | null };

/**
 * When an item's data is from.
 *
 * STAC gives an Item two ways to say this and requires the unused one be null:
 * an instant in `datetime`, or a range in `start_datetime`/`end_datetime` with
 * `datetime` null. Reading `datetime` alone therefore shows *no* date for a
 * dataset that covers a period — which is what a standards-conformant harvest
 * produces for anything measured over time.
 */
export const itemPeriod = (item: CatalogItem): CatalogPeriod | undefined => {
  const { datetime, start_datetime: start, end_datetime: end } = item.properties;
  if (start || end) return { start: start ?? datetime, end: end ?? datetime };
  return datetime ? { start: datetime, end: datetime } : undefined;
};

/**
 * When a dataset's data is from: the envelope of its layers' dates.
 *
 * The served `extent.temporal` is already that envelope — the mirror derives it
 * from the members and keeps the published extent only as a fallback (mirror v6),
 * because a Collection's own extent is `[start, null]` on 3,766 of 3,834 rows
 * with the start in the harvest year on 799 of them. Reading it directly made a
 * single-layer dataset from 2001 render as "since 2001".
 *
 * `members` still matters where they are in hand and the row is not: a bundle
 * page has the layers, and a period computed from them cannot disagree with the
 * dates listed beneath it.
 */
export const datasetPeriod = (
  collection: CatalogCollection | undefined,
  members: CatalogItem[] = []
): CatalogPeriod | undefined => {
  const interval = collection?.extent?.temporal?.interval?.[0];
  if (interval && (interval[0] || interval[1])) {
    return { start: interval[0], end: interval[1] };
  }
  const periods = members.map(itemPeriod).filter((p): p is CatalogPeriod => !!p);
  if (!periods.length) return undefined;
  const starts = periods.map((p) => p.start).filter((v): v is string => !!v).sort();
  const ends = periods.map((p) => p.end).filter((v): v is string => !!v).sort();
  return { start: starts[0], end: ends[ends.length - 1] };
};
