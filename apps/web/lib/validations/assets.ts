import { z } from "zod";

export const ASSETS_MAX_FILE_SIZE_MB = 4;
export const DOCUMENTS_MAX_FILE_SIZE_MiB = 50;

export const DOCUMENT_MIME_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
];

export const DOCUMENT_ACCEPT = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/msword": [".doc"],
};

export const assetTypeEnum = z.enum(["image", "icon", "document"]);

export const uploadedAssetSchema = z.object({
  id: z.string().uuid().optional(),
  file_name: z.string().max(255),
  display_name: z.string().max(255).nullable().optional(),
  category: z.string().max(100).nullable().optional(),
  folder_id: z.string().uuid().nullable().optional(),
  user_id: z.string().uuid(),
  url: z.string().url(),
  mime_type: z.string().max(100),
  file_size: z.number().int().nonnegative(),
  asset_type: assetTypeEnum,
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),
});

export type UploadedAsset = z.infer<typeof uploadedAssetSchema>;
export type AssetTypeEnum = z.infer<typeof assetTypeEnum>;
