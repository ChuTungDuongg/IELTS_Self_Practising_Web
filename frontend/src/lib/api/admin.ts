import { z } from "zod";
import { userSchema } from "./auth";
import { profileFieldsSchema } from "./profile";
import { analyticsSchema, type AnalyticsDashboard } from "./analytics";
import type { HistoryResponse } from "./history";
import { apiRequest, type ApiRequester } from "./client";

const skillSchema = z.enum(["READING", "LISTENING", "WRITING"]);
const statsSchema = z.object({
  total_users: z.number().int(),
  active_users: z.number().int(),
  users_with_attempts: z.number().int(),
  total_attempts: z.number().int(),
  active_attempts: z.number().int(),
  completed_attempts: z.number().int(),
  completed_full_mocks: z.number().int(),
  attempts_by_skill: z.record(skillSchema, z.number().int()),
});
const adminUserSchema = userSchema.pick({
  id: true, email: true, display_name: true, role: true, is_active: true,
  created_at: true, last_login_at: true,
}).extend({ attempt_count: z.number().int(), last_activity_at: z.string().nullable() });
const userListSchema = z.object({
  items: z.array(adminUserSchema), total: z.number().int(), offset: z.number().int(), limit: z.number().int(),
});

export type AdminStats = z.infer<typeof statsSchema>;
export type AdminUserList = z.infer<typeof userListSchema>;
export type AdminUserDetail = { user: z.infer<typeof profileFieldsSchema>; history: HistoryResponse; analytics: AnalyticsDashboard };

export async function getAdminStats(request: ApiRequester = apiRequest) {
  return statsSchema.parse(await request<unknown>("/admin/stats"));
}

export async function getAdminUsers(
  options: { search?: string; isActive?: boolean; offset?: number } = {},
  request: ApiRequester = apiRequest,
) {
  const query = new URLSearchParams();
  if (options.isActive !== undefined) query.set("is_active", String(options.isActive));
  if (options.search?.trim()) query.set("search", options.search.trim());
  if (options.offset && options.offset > 0) query.set("offset", String(options.offset));
  const suffix = query.size ? `?${query.toString().replace(/\+/g, "%20")}` : "";
  return userListSchema.parse(await request<unknown>(`/admin/users${suffix}`));
}

export async function getAdminUser(userId: string, request: ApiRequester = apiRequest): Promise<AdminUserDetail> {
  const data = await request<Record<string, unknown>>(`/admin/users/${encodeURIComponent(userId)}`);
  return {
    user: profileFieldsSchema.parse(data.user),
    history: data.history as HistoryResponse,
    analytics: analyticsSchema.parse(data.analytics),
  };
}

export async function updateAdminUser(
  userId: string,
  update: { role?: "USER" | "ADMIN"; is_active?: boolean },
) {
  return userSchema.parse(await apiRequest<unknown>(`/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  }));
}

export async function deleteAdminUser(userId: string): Promise<void> {
  await apiRequest<unknown>(`/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
}
