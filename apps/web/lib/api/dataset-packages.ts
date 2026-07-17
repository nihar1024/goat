import useSWR from "swr";

import { apiRequestAuth, fetcher } from "@/lib/api/fetcher";

export const DATASET_PACKAGES_API_BASE_URL = new URL(
  "api/v2/dataset-package",
  process.env.NEXT_PUBLIC_API_URL
).href;

export interface DatasetPackageImportRequest {
  s3_key: string;
  folder_id: string;
  name: string;
  description?: string;
  /** Street network package to link as a dependency (PT networks). */
  street_network_package_id?: string;
}

export interface DatasetPackageRead {
  id: string;
  name: string;
  folder_id: string;
  dataset_package_type: string;
  status: string;
  description?: string | null;
  thumbnail_url?: string;
  created_at?: string;
  updated_at?: string;
  owned_by?: { id: string; firstname: string; lastname: string; avatar?: string | null } | null;
}

export interface DatasetPackageImportResponse {
  package: DatasetPackageRead;
  /** Windmill job id for the background ingest; poll for status. */
  job_id: string | null;
}

/**
 * A dataset package type the upload flow can recognise from a file. Adding a new
 * type (OSM, PBF, …) is a new entry here — the upload UI stays generic. The
 * backend independently re-infers and validates the type from the file, so this
 * is only for routing the upload and showing the detected type.
 */
export interface DatasetPackageTypeDef {
  /** Type id, matching the backend's DatasetPackageTypeName. */
  type: string;
  /** i18n key for the type's display name (e.g. "pt_network_gtfs"). */
  labelKey: string;
  /** Short format label for the "supported formats" hint. */
  uploadHint: string;
  /** Whether an uploaded file is this dataset package type. */
  matches: (file: File) => boolean;
}

export const DATASET_PACKAGE_TYPES: DatasetPackageTypeDef[] = [
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
 * Detect which dataset package type an uploaded file is, or null when it's a
 * plain single-layer dataset.
 */
export const detectDatasetPackageType = (
  file: File | null | undefined
): DatasetPackageTypeDef | null =>
  file ? DATASET_PACKAGE_TYPES.find((t) => t.matches(file)) ?? null : null;

/**
 * True when a content tile is a dataset package rather than a layer. The layer
 * listing endpoint tags package items with `content_type: "dataset_package"`.
 */
export const isDatasetPackageTile = (item: unknown): boolean =>
  !!item &&
  typeof item === "object" &&
  (item as { content_type?: string }).content_type === "dataset_package";

export const requestDatasetPackageImport = async (
  req: DatasetPackageImportRequest
): Promise<DatasetPackageImportResponse> => {
  const response = await apiRequestAuth(`${DATASET_PACKAGES_API_BASE_URL}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Dataset package import failed: ${errorText}`);
  }

  return (await response.json()) as DatasetPackageImportResponse;
};

/** Delete a dataset package and all its member layers (owner only). */
export const deleteDatasetPackage = async (datasetPackageId: string): Promise<void> => {
  const response = await apiRequestAuth(`${DATASET_PACKAGES_API_BASE_URL}/${datasetPackageId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Dataset package delete failed: ${errorText}`);
  }
};

/** Update a dataset package (e.g. move to another folder). Owner only. */
export const updateDatasetPackage = async (
  datasetPackageId: string,
  payload: { name?: string; description?: string; folder_id?: string }
): Promise<DatasetPackageRead> => {
  const response = await apiRequestAuth(`${DATASET_PACKAGES_API_BASE_URL}/${datasetPackageId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Dataset package update failed: ${errorText}`);
  }
  return (await response.json()) as DatasetPackageRead;
};

// --- Sharing (grant-based, same model as folders) --------------------------

export type DatasetPackageGranteeType = "team" | "organization";
export type DatasetPackageRole = "dataset-package-viewer" | "dataset-package-editor";

export interface DatasetPackageGrant {
  grantee_type: DatasetPackageGranteeType;
  grantee_id: string;
  grantee_name: string;
  role: DatasetPackageRole;
}

export interface DatasetPackageGrantsResponse {
  grants: DatasetPackageGrant[];
}

/** Fetch the grants (team/org access) on a dataset package. Owner only. */
export const useDatasetPackageGrants = (datasetPackageId: string | null) =>
  useSWR<DatasetPackageGrantsResponse>(
    datasetPackageId ? `${DATASET_PACKAGES_API_BASE_URL}/${datasetPackageId}/share` : null,
    fetcher
  );

/** Grant (or update) a team/org's access to a dataset package. */
export const shareDatasetPackageGrant = async (
  datasetPackageId: string,
  payload: {
    grantee_type: DatasetPackageGranteeType;
    grantee_id: string;
    role: DatasetPackageRole;
  }
): Promise<DatasetPackageGrantsResponse> => {
  const response = await apiRequestAuth(`${DATASET_PACKAGES_API_BASE_URL}/${datasetPackageId}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to share dataset package");
  }
  return response.json();
};

/** Revoke a team/org's access to a dataset package. */
export const deleteDatasetPackageGrant = async (
  datasetPackageId: string,
  granteeType: string,
  granteeId: string
): Promise<void> => {
  const response = await apiRequestAuth(
    `${DATASET_PACKAGES_API_BASE_URL}/${datasetPackageId}/share/${granteeType}/${granteeId}`,
    { method: "DELETE" }
  );
  if (!response.ok && response.status !== 204) {
    throw new Error("Failed to remove dataset package access");
  }
};
