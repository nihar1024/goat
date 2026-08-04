import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import type { CatalogKind } from "@/lib/catalog/kind";
import type { CatalogPeriod } from "@/lib/catalog/period";
import type {
  CatalogCollection,
  CatalogItem,
  CatalogLink,
  CatalogTheme,
} from "@/lib/validations/catalog";

/**
 * Turning catalog values into text a person reads.
 *
 * Every catalog surface needs the same handful of conversions — a layer type, a
 * theme concept, a country code, a harvest timestamp — and they must agree
 * between the result cards and the detail views or the same dataset appears to
 * say two different things. The app already has vocabularies for all of them
 * (`metadata.type`, `metadata.data_category`, the `countries` and `languages`
 * namespaces), so this resolves against those and falls back to the raw value
 * rather than inventing labels.
 */
export const useCatalogLabels = () => {
  const { t, i18n } = useTranslation(["common", "countries", "languages"]);

  /** Translate if the vocabulary has the value; otherwise show what was served. */
  const translate = useCallback(
    (path: string, raw: string) => (i18n.exists(path) ? t(path) : raw),
    [i18n, t]
  );

  const year = (iso: string) => String(new Date(iso).getUTCFullYear());
  const sameDay = (a: string, b: string) => a === b;
  /**
   * A value that is a year with a day bolted on: 1 January, midnight, UTC — which
   * is how the harvester writes a year-precision date, on 4,689 of 10,793 layers.
   *
   * Tested in UTC even though the day is *rendered* in the reader's timezone.
   * Each rule sits where its truth is: whether the stored value carries only a
   * year is a fact about the value, and which day it falls on is a question for
   * the reader's clock. Testing this locally would make the answer depend on the
   * viewer — 2015-01-01T00:00:00Z is 01:00 in Berlin, and no longer midnight.
   */
  const yearOnly = (iso: string) => {
    const at = new Date(iso);
    return (
      at.getUTCMonth() === 0 &&
      at.getUTCDate() === 1 &&
      at.getUTCHours() === 0 &&
      at.getUTCMinutes() === 0
    );
  };
  const exactDay = (iso: string, locale: string) =>
    new Date(iso).toLocaleDateString(locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });

  return useMemo(
    () => ({
      /**
       * A dataset's kind, from `catalogKindOf` — never from `goat:layerType`
       * directly, which is inherited from the collection. `undefined` when the
       * kind is unknown, so a caller shows nothing rather than a guess.
       */
      kindLabel: (kind: CatalogKind) => {
        if (kind === "bundle") return t("common:catalog_bundle");
        if (kind === "unknown") return undefined;
        const key = kind === "vector" ? "feature" : kind;
        return translate(`common:metadata.type.${key}`, key);
      },

      /** A theme concept id as a category name. */
      conceptLabel: (concept?: string | null) =>
        concept
          ? translate(`common:metadata.data_category.${concept}`, concept)
          : undefined,

      /**
       * The data category: the first concept of the first theme block.
       *
       * `themes` carries the STAC structure; the mirror's flat `category` column
       * is internal and only backs the facet.
       */
      categoryLabel: (themes?: CatalogTheme[] | null) => {
        const concept = themes?.[0]?.concepts?.[0]?.id;
        if (!concept) return undefined;
        return translate(`common:metadata.data_category.${concept}`, concept);
      },

      /** A `goat:geographical_code` (ISO 3166-1 alpha-2) as a country name. */
      regionLabel: (code?: string | null) =>
        code ? translate(`countries:${code.toUpperCase()}`, code) : undefined,

      languageLabel: (code?: string | null) =>
        code ? translate(`languages:${code}`, code) : undefined,

      geometryLabel: (geometryType?: string | null) =>
        geometryType
          ? translate(`common:metadata.geometry_type.${geometryType}`, geometryType)
          : undefined,

      /**
       * A licence, where the row states one.
       *
       * `undefined` for STAC's two placeholders. `other` and `proprietary` mean
       * "not one of the known identifiers", i.e. unknown — and 3,659 of the
       * catalog's 3,834 datasets say `other`, so printing it would fill a cell on
       * 95% of cards with a word that answers nothing. The cell disappears
       * instead, and appears where a real licence is published.
       *
       * A URL is reduced to its last path segment: 59 datasets state
       * `http://www.opendefinition.org/licenses/cc-by`, which is not a valid STAC
       * licence (the spec wants an SPDX id) but does name one legibly once the
       * host is dropped.
       */
      licenseLabel: (license?: string | null) => {
        if (!license) return undefined;
        const value = license.trim();
        if (/^(other|proprietary)$/i.test(value)) return undefined;
        if (!/^https?:\/\//i.test(value)) return value;
        const tail = value.replace(/\/+$/, "").split("/").pop();
        return tail ? tail.toUpperCase() : undefined;
      },

      /** Date only: catalog timestamps are harvest clocks, so the time misleads. */
      formatDate: (iso?: string | null) =>
        iso ? new Date(iso).toLocaleDateString(i18n.language) : undefined,

      /**
       * A period as one line, for a card: "10 Jun 2001", "2001", "2014 – 2021".
       *
       * A real date is shown as a real date, in the reader's locale with the month
       * spelled short — `10 Jun 2001` rather than `6/10/2001`, which reads as
       * 6 October to half of Europe. Rendered in the reader's own timezone, which
       * is what recovers the intended day: these values are local midnights
       * published as UTC (`2001-06-10T22:00:00Z` is 11 June in Berlin).
       *
       * A value of 1 January at midnight is a year with a day bolted on -- 4,689
       * of 10,793 layers are dated that way -- so it prints as its year. A span
       * prints as its two years, since the days at either end of a multi-year
       * period are noise.
       *
       * The open-ended forms remain for an Item that publishes `start_datetime`
       * with no end. A *dataset* cannot reach them: its period is the envelope of
       * its layers' dates (mirror v6), so it has two real bounds or none.
       */
      formatPeriod: (period?: CatalogPeriod) => {
        if (!period) return undefined;
        const { start, end } = period;
        if (!start && !end) return undefined;
        if (start && end) {
          if (year(start) !== year(end)) return `${year(start)} – ${year(end)}`;
          if (!sameDay(start, end)) return year(start);
          return yearOnly(start) ? year(start) : exactDay(start, i18n.language);
        }
        return start
          ? t("common:catalog_period_since", { year: year(start) })
          : t("common:catalog_period_until", { year: year(end as string) });
      },

      /**
       * The same period for a detail sidebar, with the heading it deserves.
       *
       * The heading follows the **value**, not the container: a single date is a
       * reference year (the app's own field name for it, `data_reference_year`),
       * and a span is a period. Binding it to the layer count instead would
       * mislabel both ends of the catalog -- 3,818 of 3,834 datasets have every
       * layer on one date, bundles included, and 70 single layers carry a range
       * of their own.
       *
       * A single value states the year here, not the day, because that is what
       * the heading claims and what the source reliably knows. The card has the
       * room to be more precise; a labelled row should not be more precise than
       * its label.
       */
      periodField: (period?: CatalogPeriod) => {
        if (!period) return undefined;
        const { start, end } = period;
        if (!start && !end) return undefined;
        if (start && end && year(start) === year(end)) {
          return {
            labelKey: "common:metadata.headings.data_reference_year",
            value: year(start),
          };
        }
        const value =
          start && end
            ? `${year(start)} – ${year(end)}`
            : start
              ? t("common:catalog_period_since", { year: year(start) })
              : t("common:catalog_period_until", { year: year(end as string) });
        return { labelKey: "common:catalog_datetime", value };
      },

      formatCount: (count?: number | null) =>
        typeof count === "number" ? count.toLocaleString(i18n.language) : undefined,
    }),
    [i18n.language, t, translate]
  );
};

/** The href of a link relation, if the catalog published one. */
export const linkHref = (links: CatalogLink[] | undefined, rel: string) =>
  links?.find((link) => link.rel === rel)?.href;

/**
 * A dataset's descriptive text and keywords.
 *
 * Both live on the **collection**, not the item: the harvester publishes one
 * description per source dataset, and an item is one layer of it. For a
 * single-layer dataset the collection *is* the dataset, so reading through to it
 * is correct rather than a fallback — without this the Description card is empty
 * on essentially every item (the published item carries one on 0.2%; the
 * mirror inherits the dataset's, which is why a card is never blank).
 */
export const describedBy = (item?: CatalogItem, collection?: CatalogCollection) => ({
  description: item?.properties.description || collection?.description || undefined,
  keywords: item?.properties.keywords?.length
    ? item.properties.keywords
    : (collection?.keywords ?? undefined),
});
