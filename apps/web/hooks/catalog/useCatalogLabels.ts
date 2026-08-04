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
       * A period as one line: "12/03/2021", "2015", "2014 – 2021", "since 2020".
       *
       * Precision follows what the period actually pins down. A single day is a
       * date. A span is years — "01/01/2014 – 31/12/2021" says "2014 – 2021"
       * with four times the ink, and a span inside one year is that year rather
       * than its first day, which would read as an instant it is not. An open
       * bound is stated as open rather than dropped: "since 2020" and "2020"
       * mean different things and the dataset published the difference.
       */
      formatPeriod: (period?: CatalogPeriod) => {
        if (!period) return undefined;
        const { start, end } = period;
        if (!start && !end) return undefined;
        const year = (iso: string) => String(new Date(iso).getUTCFullYear());
        if (start && end) {
          if (start === end) return new Date(start).toLocaleDateString(i18n.language);
          return year(start) === year(end) ? year(start) : `${year(start)} – ${year(end)}`;
        }
        return start
          ? t("common:catalog_period_since", { year: year(start) })
          : t("common:catalog_period_until", { year: year(end as string) });
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
