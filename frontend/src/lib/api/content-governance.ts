import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { appendPageQuery, type PageOptions } from "./pagination";
export const moderationSchema = z.object({
  id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  scope: z.enum(["CLASSROOM", "PUBLIC"]),
  status: z.enum(["PENDING", "APPROVED", "REJECTED", "CANCELLED", "REVOKED"]),
  submitted_by_user_id: z.string().uuid(),
  submitted_at: z.string(),
  submit_note: z.string().nullable(),
  reviewed_by_user_id: z.string().uuid().nullable(),
  reviewed_at: z.string().nullable(),
  review_note: z.string().nullable(),
  cancelled_at: z.string().nullable().optional(),
  revoked_at: z.string().nullable(),
  revoked_by_user_id: z.string().uuid().nullable(),
  revoke_reason: z.string().nullable(),
  test_id: z.string().uuid().nullable().optional(),
  test_title: z.string().nullable().optional(),
  version_number: z.number().nullable().optional(),
});
export type ModerationRequest = z.infer<typeof moderationSchema>;
export async function getVersionModeration(versionId: string, request: ApiRequester = apiRequest) {
  return z.array(moderationSchema).parse(await request<unknown>(`/test-versions/${encodeURIComponent(versionId)}/moderation-requests`));
}
export async function submitModeration(versionId: string, scope: "CLASSROOM" | "PUBLIC", note: string) {
  return moderationSchema.parse(await apiRequest<unknown>(`/test-versions/${encodeURIComponent(versionId)}/moderation-requests`, { method: "POST", body: JSON.stringify({ scope, note: note.trim() || null }) }));
}
export async function cancelModeration(id: string) {
  return moderationSchema.parse(await apiRequest<unknown>(`/test-moderation-requests/${encodeURIComponent(id)}/cancel`, { method: "POST" }));
}
export async function listModeration(request: ApiRequester = apiRequest, status: ModerationRequest["status"] = "PENDING", options?: PageOptions) {
  return z.array(moderationSchema).parse(await request<unknown>(appendPageQuery(`/admin/test-moderation-requests?status=${status}`, options)));
}
export async function getModeration(id: string, request: ApiRequester = apiRequest) {
  return moderationSchema.parse(await request<unknown>(`/admin/test-moderation-requests/${encodeURIComponent(id)}`));
}
export async function reviewModeration(id: string, action: "approve" | "reject" | "revoke", note: string) {
  return moderationSchema.parse(await apiRequest<unknown>(`/admin/test-moderation-requests/${encodeURIComponent(id)}/${action}`, { method: "POST", body: JSON.stringify({ note: note.trim() || null }) }));
}
