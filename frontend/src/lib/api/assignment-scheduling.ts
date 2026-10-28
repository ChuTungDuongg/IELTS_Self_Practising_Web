import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { assignmentSchema } from "./classrooms";

export const scheduleSchema = z.object({ available_from: z.string().nullable(), due_at: z.string().nullable(), cutoff_at: z.string().nullable(), max_attempts: z.number().int().nullable(), allow_late_submission: z.boolean() });
export type SchedulePolicy = z.infer<typeof scheduleSchema>;
export const progressSchema = z.object({ assignment_id: z.string().uuid(), availability_status: z.enum(["SCHEDULED", "OPEN", "OVERDUE", "CLOSED", "ARCHIVED"]), submission_status: z.enum(["NOT_STARTED", "IN_PROGRESS", "SUBMITTED_ON_TIME", "SUBMITTED_LATE", "SUBMITTED_NOT_ACCEPTED", "MISSED"]), available_from: z.string().nullable(), effective_due_at: z.string().nullable(), effective_cutoff_at: z.string().nullable(), max_attempts: z.number().int().nullable(), attempts_used: z.number().int(), attempts_remaining: z.number().int().nullable(), can_start: z.boolean(), start_blocked_reason: z.string().nullable(), can_resume: z.boolean(), latest_attempt_id: z.string().uuid().nullable(), latest_session_id: z.string().uuid().nullable(), resume_attempt_id: z.string().uuid().nullable(), resume_session_id: z.string().uuid().nullable(), result_attempt_id: z.string().uuid().nullable(), completed_at: z.string().nullable(), late: z.boolean(), accepted: z.boolean(), historical: z.boolean() });
export type AssignmentProgress = z.infer<typeof progressSchema>;
export const extensionSchema = z.object({ id: z.string().uuid(), assignment_id: z.string().uuid(), student_id: z.string().uuid(), override_due: z.boolean(), due_at_override: z.string().nullable(), override_cutoff: z.boolean(), cutoff_at_override: z.string().nullable(), additional_attempts: z.number().int(), reason: z.string().nullable(), revoked: z.boolean(), revision: z.number().int(), created_by_user_id: z.string().uuid(), created_at: z.string(), updated_at: z.string() });
export type AssignmentExtension = z.infer<typeof extensionSchema>;
export type ExtensionInput = Pick<AssignmentExtension, "override_due" | "due_at_override" | "override_cutoff" | "cutoff_at_override" | "additional_attempts" | "reason">;
const monitorSchema = z.object({ items: z.array(z.object({ student_id: z.string().uuid(), display_name: z.string(), joined_at: z.string().nullable(), active_member: z.boolean(), progress: progressSchema, extension: extensionSchema.nullable() })), total: z.number().int(), summary: z.record(z.string(), z.number()) });
export type AssignmentMonitoring = z.infer<typeof monitorSchema>;
const calendarSchema = z.object({ items: z.array(z.object({ assignment_id: z.string().uuid(), title: z.string(), kind: z.enum(["AVAILABLE", "DUE", "CUTOFF"]), at: z.string(), progress: progressSchema.nullable() })), total: z.number().int() });
export type AssignmentCalendar = z.infer<typeof calendarSchema>;
const base = (room: string) => `/classrooms/${encodeURIComponent(room)}`;
const path = (room: string, id: string) => `${base(room)}/assignments/${encodeURIComponent(id)}`;
export async function getAssignmentProgress(room: string, options: { offset?: number; limit?: number; assignmentIds?: string[] } = {}, signal?: AbortSignal, request: ApiRequester = apiRequest) {
  const query = new URLSearchParams({ limit: String(options.limit ?? 100), offset: String(options.offset ?? 0) });
  options.assignmentIds?.forEach(id => query.append("assignment_ids", id));
  return z.object({ items: z.array(progressSchema), total: z.number() }).parse(await request(`${base(room)}/assignment-progress?${query}`, { signal }));
}
export async function updateAssignmentSchedule(room: string, id: string, input: SchedulePolicy & { expected_revision: number; reason?: string | null }) {
  return assignmentSchema.parse(await apiRequest(path(room, id), { method: "PATCH", body: JSON.stringify(input) }));
}
export async function getMonitoring(room: string, id: string, options: { status: string; search: string; offset: number }, signal?: AbortSignal) {
  return monitorSchema.parse(await apiRequest(`${path(room, id)}/monitoring?${new URLSearchParams({ ...options, offset: String(options.offset), limit: "25" })}`, { signal }));
}
export async function saveExtension(room: string, id: string, student: string, input: ExtensionInput) {
  return extensionSchema.parse(await apiRequest(`${path(room, id)}/extensions/${encodeURIComponent(student)}`, { method: "PUT", body: JSON.stringify(input) }));
}
export async function revokeExtension(room: string, id: string, student: string) {
  return extensionSchema.parse(await apiRequest(`${path(room, id)}/extensions/${encodeURIComponent(student)}`, { method: "DELETE" }));
}
export async function getAssignmentCalendar(room: string, start: string, end: string, offset = 0, signal?: AbortSignal, request: ApiRequester = apiRequest) {
  return calendarSchema.parse(await request(`${base(room)}/assignment-calendar?${new URLSearchParams({ start, end, limit: "50", offset: String(offset) })}`, signal ? { signal } : undefined));
}

export function serializeSchedule(form: FormData): SchedulePolicy {
  const instant = (name: string) => { const value = String(form.get(name) ?? ""); if (!value) return null; const date = new Date(value); if (!Number.isFinite(date.valueOf()) || localDateTime(date.toISOString()) !== value) throw new Error("date"); return date.toISOString(); };
  const policy = { available_from: instant("available_from"), due_at: instant("due_at"), cutoff_at: instant("cutoff_at"), max_attempts: form.get("max_attempts") ? Number(form.get("max_attempts")) : null, allow_late_submission: form.get("allow_late_submission") === "on" };
  if (policy.available_from && policy.due_at && policy.available_from >= policy.due_at || policy.due_at && policy.cutoff_at && policy.due_at > policy.cutoff_at || policy.available_from && policy.cutoff_at && policy.available_from >= policy.cutoff_at || policy.max_attempts !== null && (!Number.isInteger(policy.max_attempts) || policy.max_attempts < 1 || policy.max_attempts > 10000)) throw new Error("schedule");
  return policy;
}
export function localDateTime(value?: string | null): string { if (!value) return ""; const date = new Date(value); return new Date(date.valueOf() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16); }
