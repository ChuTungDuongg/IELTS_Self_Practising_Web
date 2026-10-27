import { z } from "zod";
import { apiRequest, apiResponse, type ApiRequester } from "./client";
import { testSchema } from "./schema";

const id = z.string().uuid(), count = z.number().int().nonnegative();
export const selectionSchema = z.enum(["LATEST_ACCEPTED", "FIRST_ACCEPTED", "BEST_ACCEPTED"]);
export const componentSchema = z.object({ attempt_id: id, skill: z.string(), band: z.number().nullable(), raw_score: z.number().nullable(), max_score: z.number().nullable(), provenance: z.string(), task_score: z.number().nullable() });
export const gradeSchema = z.object({ assignment_id: id, root_id: id, kind: z.enum(["ATTEMPT", "SESSION"]), result_attempt_id: id.nullable(), skill: z.string(), scope: z.string(), context: z.string(), band: z.number().nullable(), raw_score: z.number().nullable(), max_score: z.number().nullable(), provenance: z.enum(["OBJECTIVE", "HUMAN_FINAL", "PENDING_HUMAN", "UNAVAILABLE"]), finished_at: z.string(), accepted: z.boolean(), late: z.boolean(), submission_status: z.string(), mixed_context_fallback: z.boolean(), breakdown: z.array(componentSchema) });
const columnSchema = z.object({ id, title: z.string(), grade_selection: selectionSchema, policy_revision: count });
export const cellSchema = z.object({ assignment_id: id, submission_status: z.string(), attempts_used: count, eligible: z.boolean(), score: gradeSchema.nullable() });
export const gradebookSchema = z.object({ assignments: z.array(columnSchema), students: z.array(z.object({ student_id: id, display_name: z.string(), active_member: z.boolean(), cells: z.array(cellSchema) })), total_students: count, total_assignments: count });
export const profileSchema = z.object({ student_id: id, display_name: z.string(), active_member: z.boolean(), counts: z.record(z.string(), count), assignments: z.array(cellSchema), history: z.array(gradeSchema), total_assignments: count, total_history: count, assignment_offset: count, history_offset: count });
const staffInputSchema = z.object({ staff_role: z.enum(["CO_TEACHER", "TEACHING_ASSISTANT"]), content_manage: z.boolean(), discussion_moderate: z.boolean(), analytics_view: z.boolean(), learning_plans_manage: z.boolean() });
export const staffSchema = staffInputSchema.extend({ id, classroom_id: id, classroom_name: z.string(), user_id: id, display_name: z.string(), email: z.string(), invited_by_user_id: id, status: z.enum(["PENDING", "ACCEPTED", "DECLINED", "CANCELLED", "REVOKED"]), created_at: z.string(), accepted_at: z.string().nullable(), revoked_at: z.string().nullable() });
export type Gradebook = z.infer<typeof gradebookSchema>;
export type Grade = z.infer<typeof gradeSchema>;
export type AcademicProfile = z.infer<typeof profileSchema>;
export type Staff = z.infer<typeof staffSchema>;
export type StaffInput = z.infer<typeof staffInputSchema>;
export type GradeFilters = { search?: string; assignment_id?: string; skill?: string; status?: string; sort?: string; offset?: number; assignment_offset?: number };
export const lmsPath = (room: string) => `/classrooms/${encodeURIComponent(room)}`;
export function queryString(filters: Record<string, string | number | undefined>) { const params = new URLSearchParams(); for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== "") params.set(key, String(value)); return params.toString(); }
export async function getGradebook(room: string, filters: GradeFilters, signal?: AbortSignal) { return gradebookSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/gradebook?${queryString(filters)}`, { signal })); }
export async function exportGradebook(room: string, filters: GradeFilters) { return (await apiResponse(`${lmsPath(room)}/gradebook/export?${queryString(filters)}`)).blob(); }
export async function updateGradePolicy(room: string, assignment: string, input: { grade_selection: z.infer<typeof selectionSchema>; expected_revision: number }) { return columnSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/assignments/${assignment}/grade-policy`, { method: "PATCH", body: JSON.stringify(input) })); }
export async function getAcademicProfile(room: string, student: string, filters: { assignment_offset?: number; history_offset?: number } = {}, signal?: AbortSignal) { return profileSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/students/${encodeURIComponent(student)}/academic-profile?${queryString(filters)}`, { signal })); }
export async function getStaff(room: string, signal?: AbortSignal) { return z.array(staffSchema).parse(await apiRequest<unknown>(`${lmsPath(room)}/staff`, { signal })); }
export async function inviteStaff(room: string, input: StaffInput & { email: string }) { return staffSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/staff`, { method: "POST", body: JSON.stringify(input) })); }
export async function updateStaff(room: string, staff: string, input: StaffInput) { return staffSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/staff/${staff}`, { method: "PATCH", body: JSON.stringify(input) })); }
export async function revokeStaff(room: string, staff: string) { return staffSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/staff/${staff}`, { method: "DELETE" })); }
export async function respondStaff(room: string, staff: string, accept: boolean) { return staffSchema.parse(await apiRequest<unknown>(`${lmsPath(room)}/staff/${staff}/${accept ? "accept" : "decline"}`, { method: "POST" })); }
export async function myStaffInvitations(request: ApiRequester = apiRequest) { return z.array(staffSchema).parse(await request<unknown>("/me/classroom-staff-invitations")); }
export async function assignableTests(room: string, request: ApiRequester = apiRequest) { return z.array(testSchema).parse(await request<unknown>(`${lmsPath(room)}/assignable-tests`)); }
