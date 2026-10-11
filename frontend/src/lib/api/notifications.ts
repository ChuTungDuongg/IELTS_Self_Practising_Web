import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { appendPageQuery, type PageOptions } from "./pagination";
const notificationSchema = z.object({
  id: z.string().uuid(),
  type: z.string(),
  payload_json: z.record(z.string(), z.unknown()),
  entity_type: z.string(),
  entity_id: z.string().uuid(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});
export type Notification = z.infer<typeof notificationSchema>;
export async function listNotifications(request: ApiRequester = apiRequest, options?: PageOptions): Promise<Notification[]> {
  return z.object({ items: z.array(notificationSchema) }).parse(await request<unknown>(appendPageQuery("/notifications", options))).items;
}
export async function getUnreadNotificationCount(request: ApiRequester = apiRequest) {
  return z.object({ unread_count: z.number().int().nonnegative() }).parse(await request<unknown>("/notifications/unread-count")).unread_count;
}
export async function markNotificationRead(id: string) {
  await apiRequest(`/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
}
export async function markAllNotificationsRead() {
  await apiRequest("/notifications/read-all", { method: "POST" });
}
