import * as z from "zod";

import { contentMetadataSchema, dataLicense } from "@/lib/validations/common";

/**
 * Editable bundle metadata. The layer vocabulary restricted to fields that
 * describe a whole acquisition (a GTFS feed, an Overture extract) rather than
 * one member layer — no per-layer accuracy or geometry-specific fields.
 */
export const bundleMetadataSchema = contentMetadataSchema.extend({
  lineage: z.string().optional(),
  geographical_code: z.string().length(2).optional(),
  data_reference_year: z.coerce.number().optional(),
  distributor_name: z.string().optional(),
  distributor_email: z.string().email().optional(),
  distribution_url: z.string().url().optional(),
  license: dataLicense.optional(),
  attribution: z.string().optional(),
});

export type BundleMetadata = z.infer<typeof bundleMetadataSchema>;
