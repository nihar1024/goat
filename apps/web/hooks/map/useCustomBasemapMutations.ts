import { useCallback } from "react";
import { v4 as uuidv4 } from "uuid";

import {
  customBasemapSchema,
  type CustomBasemap,
  type Project,
} from "@/lib/validations/project";

// Accepts either (key, value, refresh?) or (partial, refresh?) — the latter
// patches multiple project fields atomically (used for the basemap create+select
// flow so the new entry is in the array AND selected in one SWR mutation).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type UpdateFn = (keyOrPartial: any, valueOrRefresh?: any, refresh?: boolean) => Promise<void> | void;

export function useCustomBasemapMutations(
  project: Project | undefined,
  onProjectUpdate: UpdateFn | undefined
) {
  const customs: CustomBasemap[] =
    (project?.custom_basemaps as CustomBasemap[] | undefined) ?? [];

  const addCustomBasemap = useCallback(
    async (
      input: Omit<CustomBasemap, "id" | "created_at" | "updated_at">,
      selectAfterAdd: boolean = false
    ): Promise<string> => {
      if (!onProjectUpdate) throw new Error("onProjectUpdate not provided");
      const now = new Date().toISOString();
      const id = uuidv4();
      const entry = customBasemapSchema.parse({
        ...input,
        id,
        created_at: now,
        updated_at: now,
      });
      const current =
        (project?.custom_basemaps as CustomBasemap[] | undefined) ?? [];
      const next = [...current, entry];
      if (selectAfterAdd) {
        await onProjectUpdate({ custom_basemaps: next, basemap: id });
      } else {
        await onProjectUpdate("custom_basemaps", next);
      }
      return id;
    },
    [project, onProjectUpdate]
  );

  const editCustomBasemap = useCallback(
    async (
      id: string,
      patch: Partial<Omit<CustomBasemap, "id" | "created_at" | "type">>
    ) => {
      if (!onProjectUpdate) throw new Error("onProjectUpdate not provided");
      const now = new Date().toISOString();
      const current =
        (project?.custom_basemaps as CustomBasemap[] | undefined) ?? [];
      const next = current.map((c) => {
        if (c.id !== id) return c;
        const merged = { ...c, ...patch, updated_at: now };
        // Re-validate post-merge so cross-variant patches (e.g. url on solid)
        // are caught here rather than at the backend.
        return customBasemapSchema.parse(merged);
      });
      await onProjectUpdate("custom_basemaps", next);
    },
    [project, onProjectUpdate]
  );

  const deleteCustomBasemap = useCallback(
    async (id: string) => {
      if (!onProjectUpdate) throw new Error("onProjectUpdate not provided");
      const current =
        (project?.custom_basemaps as CustomBasemap[] | undefined) ?? [];
      const next = current.filter((c) => c.id !== id);
      await onProjectUpdate("custom_basemaps", next);
    },
    [project, onProjectUpdate]
  );

  return { customs, addCustomBasemap, editCustomBasemap, deleteCustomBasemap };
}
