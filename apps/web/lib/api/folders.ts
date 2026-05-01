import useSWR from "swr";

import { apiRequestAuth, fetcher } from "@/lib/api/fetcher";
import type { GetContentQueryParams } from "@/lib/validations/common";
import type { FolderGrantsResponse, FolderResponse, FolderSharePayload } from "@/lib/validations/folder";

export const FOLDERS_API_BASE_URL = new URL("api/v2/folder", process.env.NEXT_PUBLIC_API_URL).href;

export const useFolders = (queryParams?: GetContentQueryParams) => {
  const { data, isLoading, error, mutate, isValidating } = useSWR<FolderResponse>(
    [`${FOLDERS_API_BASE_URL}`, queryParams],
    fetcher
  );
  return {
    folders: data,
    isLoading: isLoading,
    isError: error,
    mutate,
    isValidating,
  };
};

export const deleteFolder = async (id: string) => {
  const response = await apiRequestAuth(`${FOLDERS_API_BASE_URL}/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error("Failed to delete folder");
  }
  return await response;
};

export const createFolder = async (name: string) => {
  const response = await apiRequestAuth(`${FOLDERS_API_BASE_URL}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error("Failed to create folder");
  }
  return await response.json();
};

export const updateFolder = async (id: string, name: string) => {
  const response = await apiRequestAuth(`${FOLDERS_API_BASE_URL}/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error("Failed to update folder");
  }
  return await response.json();
};

export const getWritableFolders = (folders: FolderResponse | undefined) =>
  folders?.filter((f) => (f.is_owned && f.name !== "home") || f.role === "folder-editor") ?? [];

export const useFolderGrants = (folderId: string | null) => {
  return useSWR<FolderGrantsResponse>(
    folderId ? `${FOLDERS_API_BASE_URL}/${folderId}/share` : null,
    fetcher
  );
};

export const shareFolderGrant = async (
  folderId: string,
  payload: FolderSharePayload
): Promise<FolderGrantsResponse> => {
  const response = await apiRequestAuth(`${FOLDERS_API_BASE_URL}/${folderId}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to share folder");
  }
  return response.json();
};

export const deleteFolderGrant = async (
  folderId: string,
  granteeType: string,
  granteeId: string
): Promise<void> => {
  const response = await apiRequestAuth(
    `${FOLDERS_API_BASE_URL}/${folderId}/share/${granteeType}/${granteeId}`,
    { method: "DELETE" }
  );
  if (!response.ok && response.status !== 204) {
    throw new Error("Failed to remove folder access");
  }
};
