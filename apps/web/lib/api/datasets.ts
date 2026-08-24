import useSWR from "swr";

import { BUNDLES_API_BASE_URL } from "@/lib/api/bundles";
import { apiRequestAuth, fetcher } from "@/lib/api/fetcher";
import { LAYERS_API_BASE_URL } from "@/lib/api/layers";
import type { PaginatedQueryParams } from "@/lib/validations/common";
import type { DatasetImportRequest, PresignedPostResponse } from "@/lib/validations/datasets";
import { datasetImportRequestSchema, presignedPostResponseSchema } from "@/lib/validations/datasets";
import type { GetDatasetSchema, LayerPaginated } from "@/lib/validations/layer";


export const DATASETS_API_BASE_URL = new URL(
    "api/v2/datasets",
    process.env.NEXT_PUBLIC_API_URL
).href;

/**
 * List the caller's datasets — layers and bundles combined — from the
 * unified datasets API. Items share one shape, discriminated by `content_type`
 * ("layer" | "bundle").
 */
export const useDatasets = (
  queryParams?: PaginatedQueryParams,
  payload: GetDatasetSchema = {}
) => {
  const { data, isLoading, error, mutate, isValidating } = useSWR<LayerPaginated>(
    [DATASETS_API_BASE_URL, queryParams, payload],
    fetcher
  );
  return { datasets: data, isLoading, isError: error, mutate, isValidating };
};

/**
 * SWR filter matching every key that renders content listings: the unified
 * datasets grid (`[DATASETS_API_BASE_URL, queryParams, payload]`), layer
 * listings and bundle listings, whether the key is a bare URL, a
 * querystringed URL or an array key. Content mutations (create, rename, move,
 * delete — layer or bundle) revalidate with this so no mounted listing is
 * left showing a ghost.
 */
export const matchesContentListKey = (key: unknown): boolean => {
  const first = Array.isArray(key) ? key[0] : key;
  return (
    typeof first === "string" &&
    (first.startsWith(DATASETS_API_BASE_URL) ||
      first.startsWith(LAYERS_API_BASE_URL) ||
      first.startsWith(BUNDLES_API_BASE_URL))
  );
};

export const requestDatasetUpload = async (
    req: DatasetImportRequest
): Promise<PresignedPostResponse> => {
    // validate client input with zod first
    const validatedReq = datasetImportRequestSchema.parse(req);

    const response = await apiRequestAuth(`${DATASETS_API_BASE_URL}/request-upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(validatedReq),
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Request upload failed: ${errorText}`);
    }

    const data = await response.json();
    return presignedPostResponseSchema.parse(data);
};