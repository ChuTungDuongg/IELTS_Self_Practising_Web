import { z } from "zod";
import { API_BASE_URL, apiRequest, apiResponse, type ApiRequester } from "./client";

export const contentStatusSchema = z.enum(["DRAFT", "PUBLISHED", "ARCHIVED"]);
export type ContentStatus = z.infer<typeof contentStatusSchema>;
export const classroomPostSchema = z.object({
  id: z.string().uuid(), kind: z.enum(["ANNOUNCEMENT", "DISCUSSION", "ASSIGNMENT_ACTIVITY", "RESOURCE_ACTIVITY"]),
  title: z.string().nullable(), body: z.string(), status: contentStatusSchema, pinned: z.boolean(), locked: z.boolean().default(false),
  author_id: z.string().uuid(), author_name: z.string(), author_role: z.string(), created_at: z.string(), updated_at: z.string(),
  published_at: z.string().nullable(), comment_count: z.number().int().nonnegative(), resource_ids: z.array(z.string().uuid()), assignment_id: z.string().uuid().nullable(),
  resource: z.lazy(() => classroomResourceSchema).nullable().optional(), resource_topic: z.string().nullable().optional(),
});
export const classroomCommentSchema = z.object({
  id: z.string().uuid(), post_id: z.string().uuid(), author_id: z.string().uuid(), author_name: z.string(), body: z.string(),
  state: z.enum(["VISIBLE", "RETRACTED", "MODERATED"]), created_at: z.string(), updated_at: z.string(),
});
export const classroomSectionSchema = z.object({
  id: z.string().uuid(), classroom_id: z.string().uuid(), title: z.string(), description: z.string().nullable(), status: contentStatusSchema,
  position: z.number().int().nonnegative(), created_at: z.string(), updated_at: z.string(),
});
const httpUrlSchema = z.string().refine(value => { try { return ["http:", "https:"].includes(new URL(value).protocol); } catch { return false; } });
export const classroomResourceSchema = z.object({
  id: z.string().uuid(), classroom_id: z.string().uuid(), title: z.string(), description: z.string().nullable(), kind: z.enum(["TEXT", "LINK", "FILE"]),
  body: z.string().nullable(), url: httpUrlSchema.nullable(), status: contentStatusSchema,
  original_filename: z.string().nullable(), media_type: z.string().nullable(), size_bytes: z.number().int().nonnegative().nullable(), created_at: z.string(), updated_at: z.string(),
});
export const classworkItemSchema = z.object({
  id: z.string().uuid(), section_id: z.string().uuid().nullable(), resource_id: z.string().uuid().nullable(), assignment_id: z.string().uuid().nullable(), position: z.number().int().nonnegative(),
}).refine(item => Number(item.resource_id !== null) + Number(item.assignment_id !== null) === 1, { message: "A classwork item references one resource or assignment." });
export const classworkSchema = z.object({ revision: z.number().int().nonnegative(), sections: z.array(classroomSectionSchema), resources: z.array(classroomResourceSchema), items: z.array(classworkItemSchema), removed_assignment_ids: z.array(z.string().uuid()).optional() });
const page = <T extends z.ZodType>(schema: T) => z.object({ items: z.array(schema), next_cursor: z.string().nullable() });
export type ClassroomPost = z.infer<typeof classroomPostSchema>;
export type ClassroomComment = z.infer<typeof classroomCommentSchema>;
export type ClassroomSection = z.infer<typeof classroomSectionSchema>;
export type ClassroomResource = z.infer<typeof classroomResourceSchema>;
export type ClassworkItem = z.infer<typeof classworkItemSchema>;
export type Classwork = z.infer<typeof classworkSchema>;
export type PostInput = { kind: "ANNOUNCEMENT" | "DISCUSSION"; title?: string | null; body: string; resource_ids?: string[]; status?: "DRAFT" | "PUBLISHED" };
export type ResourceInput = { title: string; description?: string | null; kind: "TEXT" | "LINK"; body?: string | null; url?: string | null; status?: ContentStatus; section_id?: string | null };
const base = (id: string) => `/classrooms/${encodeURIComponent(id)}`;
const json = (method: string, input?: unknown): RequestInit => ({ method, ...(input === undefined ? {} : { body: JSON.stringify(input) }) });
export async function listFeed(id: string, options: { cursor?: string; status?: ContentStatus; contentKind?: ClassroomPost["kind"]; signal?: AbortSignal } = {}, request: ApiRequester = apiRequest) {
  const query = new URLSearchParams({ limit: "20" });
  if (options.cursor) query.set("cursor", options.cursor);
  if (options.status) query.set("status", options.status);
  if (options.contentKind) query.set("content_kind", options.contentKind);
  const path = `${base(id)}/feed?${query}`;
  return page(classroomPostSchema).parse(options.signal ? await request<unknown>(path, { signal: options.signal }) : await request<unknown>(path));
}
export async function getPost(id: string, postId: string, signal?: AbortSignal) { return classroomPostSchema.parse(await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}`, signal ? { signal } : undefined)); }
export async function createPost(id: string, input: PostInput) { return classroomPostSchema.parse(await apiRequest(`${base(id)}/posts`, json("POST", input))); }
export async function updatePost(id: string, postId: string, input: Omit<Partial<PostInput>, "status"> & { pinned?: boolean; locked?: boolean; status?: ContentStatus }) { return classroomPostSchema.parse(await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}`, json("PATCH", input))); }
export async function postAction(id: string, postId: string, action: "publish" | "archive" | "pin", pinned?: boolean) { return classroomPostSchema.parse(await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}/${action}`, json("POST", action === "pin" ? { pinned } : undefined))); }
export async function listComments(id: string, postId: string, cursor?: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ limit: "20" }); if (cursor) query.set("cursor", cursor);
  return page(classroomCommentSchema).parse(await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}/comments?${query}`, signal ? { signal } : undefined));
}
export async function createComment(id: string, postId: string, body: string) { return classroomCommentSchema.parse(await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}/comments`, json("POST", { body }))); }
export async function updateComment(id: string, commentId: string, body: string) { return classroomCommentSchema.parse(await apiRequest(`${base(id)}/comments/${encodeURIComponent(commentId)}`, json("PATCH", { body }))); }
export async function retractComment(id: string, commentId: string) { return classroomCommentSchema.parse(await apiRequest(`${base(id)}/comments/${encodeURIComponent(commentId)}`, json("DELETE"))); }
export async function getClasswork(id: string, request: ApiRequester = apiRequest, signal?: AbortSignal) { return classworkSchema.parse(signal ? await request<unknown>(`${base(id)}/classwork`, { signal }) : await request<unknown>(`${base(id)}/classwork`)); }
export async function createSection(id: string, input: { title: string; description?: string | null; status?: ContentStatus }) { return classroomSectionSchema.parse(await apiRequest(`${base(id)}/sections`, json("POST", input))); }
export async function updateSection(id: string, sectionId: string, input: { title?: string; description?: string | null; status?: ContentStatus }) { return classroomSectionSchema.parse(await apiRequest(`${base(id)}/sections/${encodeURIComponent(sectionId)}`, json("PATCH", input))); }
export async function reorderSections(id: string, ids: string[], expected_revision: number) { return classworkSchema.parse(await apiRequest(`${base(id)}/sections/reorder`, json("POST", { ids, expected_revision }))); }
export async function reorderItems(id: string, section_id: string | null, ids: string[], expected_revision: number) { return classworkSchema.parse(await apiRequest(`${base(id)}/items/reorder`, json("POST", { section_id, ids, expected_revision }))); }
export async function placeAssignment(id: string, section_id: string | null, assignment_id: string) { return classworkSchema.parse(await apiRequest(`${base(id)}/items`, json("POST", { section_id, assignment_id }))); }
export async function deletePost(id: string, postId: string) { await apiRequest(`${base(id)}/posts/${encodeURIComponent(postId)}`, json("DELETE")); }
export async function deleteSection(id: string, sectionId: string, revision: number) { return classworkSchema.parse(await apiRequest(`${base(id)}/sections/${encodeURIComponent(sectionId)}?expected_revision=${revision}`, json("DELETE"))); }
export async function deleteResource(id: string, resourceId: string, revision: number) { return classworkSchema.parse(await apiRequest(`${base(id)}/resources/${encodeURIComponent(resourceId)}?expected_revision=${revision}`, json("DELETE"))); }
export async function removeAssignmentItem(id: string, itemId: string, revision: number) { return classworkSchema.parse(await apiRequest(`${base(id)}/items/${encodeURIComponent(itemId)}?expected_revision=${revision}`, json("DELETE"))); }
export async function removeAssignmentReference(id: string, assignmentId: string, revision?: number) {
  const query = revision === undefined ? "" : `?expected_revision=${revision}`;
  return classworkSchema.parse(await apiRequest(`${base(id)}/assignments/${encodeURIComponent(assignmentId)}/classwork${query}`, json("DELETE")));
}
export async function createResource(id: string, input: ResourceInput) { return classroomResourceSchema.parse(await apiRequest(`${base(id)}/resources`, json("POST", input))); }
export async function updateResource(id: string, resourceId: string, input: { title?: string; description?: string | null; body?: string | null; url?: string | null; status?: ContentStatus }) { return classroomResourceSchema.parse(await apiRequest(`${base(id)}/resources/${encodeURIComponent(resourceId)}`, json("PATCH", input))); }
export async function uploadResource(id: string, input: { title: string; description?: string | null; file: File; status: ContentStatus; section_id?: string | null }) {
  const form = new FormData(); form.set("title", input.title); form.set("file", input.file); form.set("status", input.status);
  if (input.description) form.set("description", input.description); if (input.section_id) form.set("section_id", input.section_id);
  return classroomResourceSchema.parse(await apiRequest(`${base(id)}/resources/upload`, { method: "POST", body: form }));
}
// Same cookie-authenticated API origin as existing exam assets. No storage key reaches the browser.
export function resourceFileUrl(id: string, resourceId: string, inline = false) { return `${API_BASE_URL}${base(id)}/resources/${encodeURIComponent(resourceId)}/file?inline=${inline}`; }
export async function fetchResourceFile(id: string, resourceId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await apiResponse(`${base(id)}/resources/${encodeURIComponent(resourceId)}/file?inline=true`, { signal });
  return response.blob();
}
