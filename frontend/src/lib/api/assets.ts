import type { AssetModel } from "@/features/questions/types";
import { API_BASE_URL, apiRequest } from "./client";

export function uploadAsset(
  kind: "images" | "question-images" | "audio",
  testVersionId: string,
  file: File,
) {
  const body = new FormData();
  body.set("test_version_id", testVersionId);
  body.set("file", file);
  return apiRequest<AssetModel>(`/assets/${kind}`, { method: "POST", body });
}

export function assetContentUrl(asset: AssetModel): string {
  return `${API_BASE_URL}${asset.content_url}`;
}
