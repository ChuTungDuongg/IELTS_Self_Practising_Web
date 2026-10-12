import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { versionDetailSchema } from "./schema";
const classroomSchema = z.object({
  id: z.string().uuid(),
  teacher_id: z.string().uuid(),
  name: z.string(),
  description: z.string().nullable(),
  status: z.enum(["ACTIVE", "ARCHIVED"]),
  archived_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});
const invitationSchema = z.object({
  id: z.string().uuid(),
  classroom_id: z.string().uuid(),
  classroom_name: z.string(),
  invited_email: z.string(),
  status: z.enum(["PENDING", "ACCEPTED", "DECLINED", "CANCELLED"]),
  created_at: z.string()
});
const memberSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  display_name: z.string(),
  email: z.string(),
  joined_at: z.string(),
  left_at: z.string().nullable(),
  removed_by_user_id: z.string().uuid().nullable()
});
export const assignmentSchema = z.object({
  id: z.string().uuid(),
  classroom_id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  created_by_user_id: z.string().uuid(),
  version: versionDetailSchema.nullable().optional(),
  title: z.string().nullable(),
  note: z.string().nullable(),
  status: z.enum(["ACTIVE", "ARCHIVED"]),
  created_at: z.string(),
  archived_at: z.string().nullable()
});
export type Classroom = z.infer<typeof classroomSchema>;
export type ClassroomInvitation = z.infer<typeof invitationSchema>;
export type ClassroomMember = z.infer<typeof memberSchema>;
export type ClassroomAssignment = z.infer<typeof assignmentSchema>;
const resource = (id: string) => `/classrooms/${encodeURIComponent(id)}`;
const post = <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
export async function listClassrooms(request: ApiRequester = apiRequest) {
  return z.object({ items: z.array(classroomSchema) }).parse(await request<unknown>("/classrooms")).items;
}
export async function getClassroom(id: string, request: ApiRequester = apiRequest) {
  return classroomSchema.parse(await request<unknown>(resource(id)));
}
export async function createClassroom(input: {
  name: string;
  description?: string | null;
}) {
  return classroomSchema.parse(await post("/classrooms", input));
}
export async function updateClassroom(id: string, input: {
  name: string;
  description: string | null;
}) {
  return classroomSchema.parse(await apiRequest<unknown>(resource(id), { method: "PATCH", body: JSON.stringify(input) }));
}
export async function archiveClassroom(id: string) {
  return classroomSchema.parse(await post(`${resource(id)}/archive`));
}
export async function restoreClassroom(id: string) {
  return classroomSchema.parse(await post(`${resource(id)}/restore`));
}
export async function listMembers(id: string, request: ApiRequester = apiRequest) {
  return z.object({ items: z.array(memberSchema) }).parse(await request<unknown>(`${resource(id)}/members`)).items;
}
export async function removeMember(classroomId: string, userId: string) {
  await post(`${resource(classroomId)}/members/${encodeURIComponent(userId)}/remove`);
}
export async function leaveClassroom(id: string) {
  await post(`${resource(id)}/leave`);
}
export async function listInvitations(id: string, request: ApiRequester = apiRequest) {
  return z.object({ items: z.array(invitationSchema) }).parse(await request<unknown>(`${resource(id)}/invitations`)).items;
}
export async function inviteStudent(id: string, email: string) {
  return invitationSchema.parse(await post(`${resource(id)}/invitations`, { email }));
}
export async function listMyInvitations(request: ApiRequester = apiRequest) {
  return z.object({ items: z.array(invitationSchema) }).parse(await request<unknown>("/me/classroom-invitations")).items;
}
export async function acceptInvitation(id: string) {
  await post(`/classroom-invitations/${encodeURIComponent(id)}/accept`);
}
export async function declineInvitation(id: string) {
  await post(`/classroom-invitations/${encodeURIComponent(id)}/decline`);
}
export async function cancelInvitation(id: string) {
  await post(`/classroom-invitations/${encodeURIComponent(id)}/cancel`);
}
export async function listAssignments(id: string, request: ApiRequester = apiRequest) {
  return z.array(assignmentSchema).parse(await request<unknown>(`${resource(id)}/assignments`));
}
export async function createAssignment(id: string, input: {
  test_version_id: string;
  title?: string | null;
  note?: string | null;
}) {
  return assignmentSchema.parse(await post(`${resource(id)}/assignments`, input));
}
export async function archiveAssignment(classroomId: string, id: string) {
  await post(`${resource(classroomId)}/assignments/${encodeURIComponent(id)}/archive`);
}
export type AssignmentStart = {
  mode: "MODULE";
  module: "READING" | "LISTENING" | "WRITING" | "SPEAKING";
  speaking_mode?: "PRACTICE" | "EXAM";
  scope: "FULL_MODULE" | "FOCUSED_UNIT";
  focused_unit?: {
    kind: "READING_PASSAGE" | "LISTENING_PART" | "WRITING_TASK" | "SPEAKING_PROMPT";
    id: string;
  };
  timer: {
    mode: "COUNT_UP" | "COUNTDOWN";
    duration_seconds?: number;
  };
} | {
  mode: "FULL_MOCK";
};
export async function startAssignment(id: string, input: AssignmentStart) {
  return z.object({ attempt_id: z.string().uuid().nullable(), test_session_id: z.string().uuid().nullable() }).parse(await post(`/classroom-assignments/${encodeURIComponent(id)}/start`, input));
}
