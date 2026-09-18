import { apiRequest } from "./client";

export function uploadAsset(
  kind: "images" | "audio",
  testVersionId: string,
  file: File,
) {
  const body = new FormData();
  body.set("test_version_id", testVersionId);
  body.set("file", file);
  return apiRequest(`/assets/${kind}`, { method: "POST", body });
}
