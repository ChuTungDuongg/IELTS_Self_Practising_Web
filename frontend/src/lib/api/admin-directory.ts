import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";

const directoryPersonSchema = z.object({
  id: z.string(),
  display_name: z.string(),
  role: z.enum(["TEACHER", "USER"]),
  is_active: z.boolean(),
  classroom_count: z.number().int().nonnegative(),
});
const pageFields = { total: z.number().int().nonnegative(), offset: z.number().int().nonnegative(), limit: z.number().int().positive().max(100) };
const peoplePageSchema = z.object({ items: z.array(directoryPersonSchema), ...pageFields });
const classroomPageSchema = z.object({
  items: z.array(z.object({
    id: z.string(), name: z.string(), status: z.enum(["ACTIVE", "ARCHIVED"]),
    teacher: z.object({ id: z.string(), display_name: z.string() }),
    enrolled_student_count: z.number().int().nonnegative(),
  })),
  ...pageFields,
});

export type DirectoryRole = "TEACHER" | "USER";
export type DirectoryPerson = z.infer<typeof directoryPersonSchema>;
export type DirectoryPeoplePage = z.infer<typeof peoplePageSchema>;
export type DirectoryClassroomsPage = z.infer<typeof classroomPageSchema>;

function pageQuery(search?: string, offset = 0) {
  const query = new URLSearchParams();
  if (search?.trim()) query.set("search", search.trim());
  if (offset > 0) query.set("offset", String(offset));
  query.set("limit", "25");
  return query;
}

function queryString(query: URLSearchParams) {
  return query.toString().replace(/\+/g, "%20");
}

export async function getDirectoryPeople(
  options: { role: DirectoryRole; search?: string; offset?: number },
  request: ApiRequester = apiRequest,
): Promise<DirectoryPeoplePage> {
  const query = new URLSearchParams({ role: options.role });
  pageQuery(options.search, options.offset).forEach((value, name) => query.set(name, value));
  return peoplePageSchema.parse(await request<unknown>(`/admin/directory/people?${queryString(query)}`));
}

export async function getDirectoryPerson(
  personId: string,
  role: DirectoryRole,
  request: ApiRequester = apiRequest,
): Promise<DirectoryPerson> {
  return directoryPersonSchema.parse(await request<unknown>(`/admin/directory/people/${encodeURIComponent(personId)}?role=${role}`));
}

export async function getDirectoryClassrooms(
  options: { teacherId?: string; studentId?: string; search?: string; offset?: number } = {},
  request: ApiRequester = apiRequest,
): Promise<DirectoryClassroomsPage> {
  const query = new URLSearchParams();
  if (options.teacherId) query.set("teacher_id", options.teacherId);
  if (options.studentId) query.set("student_id", options.studentId);
  pageQuery(options.search, options.offset).forEach((value, name) => query.set(name, value));
  return classroomPageSchema.parse(await request<unknown>(`/admin/directory/classrooms?${queryString(query)}`));
}
