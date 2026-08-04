import useSWR from "swr";

import { CATALOG_API_BASE_URL } from "@/lib/api/catalog";
import { fetcher } from "@/lib/api/fetcher";

/**
 * The outlines *and names* of several NUTS regions, keyed by id.
 *
 * One SWR entry over the whole selection rather than a hook per region, because
 * the number of selected regions changes as the user picks and removes them and
 * hooks cannot be called conditionally. Regions are fetched in parallel and a
 * failure on one is dropped rather than failing the set: a missing outline means
 * the map draws one less shape, not a broken dialog.
 *
 * The name comes back with the geometry, which is what lets a shared link show
 * "Niederösterreich" instead of `AT12` — the URL can only carry the id, and this
 * request is being made anyway to draw the boundary.
 *
 * Immutable for the life of a mirror generation, so it never revalidates.
 */
type NutsRegionShape = { geometry?: GeoJSON.Geometry; name?: string };

export const useCatalogNutsGeometries = (nutsIds: string[]) => {
  const key = nutsIds.length && CATALOG_API_BASE_URL ? ["nuts-geometries", ...nutsIds] : null;

  const { data, isLoading, error } = useSWR<Record<string, NutsRegionShape>>(
    key,
    async ([, ...ids]: string[]) => {
      const entries = await Promise.all(
        ids.map(async (id) => {
          try {
            const feature = (await fetcher(
              `${CATALOG_API_BASE_URL}/nuts/${encodeURIComponent(id)}/geometry`
            )) as GeoJSON.Feature;
            return [
              id,
              {
                geometry: feature?.geometry,
                name: feature?.properties?.nuts_name as string | undefined,
              },
            ] as const;
          } catch {
            return [id, {}] as const;
          }
        })
      );
      return Object.fromEntries(entries);
    },
    { revalidateOnFocus: false, revalidateIfStale: false, keepPreviousData: true }
  );

  const shapes = data ?? {};
  return {
    shapes,
    geometries: Object.fromEntries(
      Object.entries(shapes).map(([id, shape]) => [id, shape.geometry])
    ),
    names: Object.fromEntries(
      Object.entries(shapes).flatMap(([id, shape]) => (shape.name ? [[id, shape.name]] : []))
    ),
    isLoading,
    isError: error,
  };
};
