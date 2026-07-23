import useSWR from "swr";

import { apiRequestAuth, fetcher } from "@/lib/api/fetcher";

export const BUNDLES_API_BASE_URL = new URL(
  "api/v2/bundle",
  process.env.NEXT_PUBLIC_API_URL
).href;

export interface BundleImportRequest {
  s3_key: string;
  folder_id: string;
  name: string;
  description?: string;
  /** Street network bundle to link as a dependency (PT networks). */
  street_network_bundle_id?: string;
}

export interface BundleRead {
  id: string;
  name: string;
  folder_id: string;
  bundle_type: string;
  status: string;
  description?: string | null;
  thumbnail_url?: string;
  created_at?: string;
  updated_at?: string;
  owned_by?: { id: string; firstname: string; lastname: string; avatar?: string | null } | null;
}

export interface BundleImportResponse {
  bundle: BundleRead;
  /** Windmill job id for the background ingest; poll for status. */
  job_id: string | null;
}

/**
 * A bundle type the upload flow can recognise from a file. Adding a new
 * type (OSM, PBF, …) is a new entry here — the upload UI stays generic. The
 * backend independently re-infers and validates the type from the file, so this
 * is only for routing the upload and showing the detected type.
 */
export interface BundleTypeDef {
  /** Type id, matching the backend's BundleTypeName. */
  type: string;
  /** i18n key for the type's display name (e.g. "pt_network_gtfs"). */
  labelKey: string;
  /** Short format label for the "supported formats" hint. */
  uploadHint: string;
  /** Whether an uploaded file is this bundle type. */
  matches: (file: File) => boolean;
}

export const BUNDLE_TYPES: BundleTypeDef[] = [
  {
    type: "pt_network_gtfs",
    labelKey: "pt_network_gtfs",
    uploadHint: "GTFS (gtfs.zip)",
    matches: (file) => {
      const name = file.name.toLowerCase();
      return name.endsWith(".zip") && name.includes("gtfs");
    },
  },
];

/**
 * Detect which bundle type an uploaded file is, or null when it's a
 * plain single-layer dataset.
 */
export const detectBundleType = (
  file: File | null | undefined
): BundleTypeDef | null =>
  file ? BUNDLE_TYPES.find((t) => t.matches(file)) ?? null : null;

/**
 * True when a content tile is a bundle rather than a layer. The layer
 * listing endpoint tags bundle items with `content_type: "bundle"`.
 */
export const isBundleTile = (item: unknown): boolean =>
  !!item &&
  typeof item === "object" &&
  (item as { content_type?: string }).content_type === "bundle";

export const requestBundleImport = async (
  req: BundleImportRequest
): Promise<BundleImportResponse> => {
  const response = await apiRequestAuth(`${BUNDLES_API_BASE_URL}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Bundle import failed: ${errorText}`);
  }

  return (await response.json()) as BundleImportResponse;
};

/** Delete a bundle and all its member layers (owner only). */
export const deleteBundle = async (bundleId: string): Promise<void> => {
  const response = await apiRequestAuth(`${BUNDLES_API_BASE_URL}/${bundleId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Bundle delete failed: ${errorText}`);
  }
};

/** Update a bundle (e.g. move to another folder). Owner only. */
export const updateBundle = async (
  bundleId: string,
  payload: { name?: string; description?: string; folder_id?: string }
): Promise<BundleRead> => {
  const response = await apiRequestAuth(`${BUNDLES_API_BASE_URL}/${bundleId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Bundle update failed: ${errorText}`);
  }
  return (await response.json()) as BundleRead;
};

// --- Sharing (grant-based, same model as folders) --------------------------

export type BundleGranteeType = "team" | "organization";
export type BundleRole = "bundle-viewer" | "bundle-editor";

export interface BundleGrant {
  grantee_type: BundleGranteeType;
  grantee_id: string;
  grantee_name: string;
  role: BundleRole;
}

export interface BundleGrantsResponse {
  grants: BundleGrant[];
}

/** Fetch the grants (team/org access) on a bundle. Owner only. */
export const useBundleGrants = (bundleId: string | null) =>
  useSWR<BundleGrantsResponse>(
    bundleId ? `${BUNDLES_API_BASE_URL}/${bundleId}/share` : null,
    fetcher
  );

/** Grant (or update) a team/org's access to a bundle. */
export const shareBundleGrant = async (
  bundleId: string,
  payload: {
    grantee_type: BundleGranteeType;
    grantee_id: string;
    role: BundleRole;
  }
): Promise<BundleGrantsResponse> => {
  const response = await apiRequestAuth(`${BUNDLES_API_BASE_URL}/${bundleId}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to share bundle");
  }
  return response.json();
};

/** Revoke a team/org's access to a bundle. */
export const deleteBundleGrant = async (
  bundleId: string,
  granteeType: string,
  granteeId: string
): Promise<void> => {
  const response = await apiRequestAuth(
    `${BUNDLES_API_BASE_URL}/${bundleId}/share/${granteeType}/${granteeId}`,
    { method: "DELETE" }
  );
  if (!response.ok && response.status !== 204) {
    throw new Error("Failed to remove bundle access");
  }
};
