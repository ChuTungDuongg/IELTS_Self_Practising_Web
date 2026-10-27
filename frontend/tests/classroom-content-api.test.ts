import { beforeEach, expect, it, vi } from "vitest";
import { getClasswork, reorderItems, createResource, resourceFileUrl, listFeed, uploadResource, fetchResourceFile } from "@/lib/api/classroom-content";
const { request, response } = vi.hoisted(() => ({ request: vi.fn(), response: vi.fn() }));
vi.mock("@/lib/api/client", async original => ({ ...await original<object>(), apiRequest: request, apiResponse: response }));
const uuid = "11111111-1111-4111-8111-111111111111";
beforeEach(() => vi.clearAllMocks());
it("validates classwork and sends revision-safe complete target lists", async () => {
  const response = { revision: 4, sections: [], resources: [], items: [] }; request.mockResolvedValue(response);
  expect(await getClasswork(uuid)).toEqual(response);
  await reorderItems(uuid, null, [uuid], 3);
  expect(request).toHaveBeenLastCalledWith(`/classrooms/${uuid}/items/reorder`, { method: "POST", body: JSON.stringify({ section_id: null, ids: [uuid], expected_revision: 3 }) });
});
it("rejects malformed classwork and keeps unsafe file destinations out of the contract", async () => {
  request.mockResolvedValue({ revision: 0, sections: [], resources: [{ id: uuid }], items: [] }); await expect(getClasswork(uuid)).rejects.toThrow();
  expect(resourceFileUrl(uuid, uuid, true)).toContain(`/classrooms/${uuid}/resources/${uuid}/file?inline=true`);
});
it("validates paginated feed and uses explicit status filters", async () => {
  request.mockResolvedValue({ items: [], next_cursor: null }); await listFeed(uuid, { status: "DRAFT", cursor: "next" });
  expect(request).toHaveBeenCalledWith(`/classrooms/${uuid}/feed?limit=20&cursor=next&status=DRAFT`);
});
it("encodes whole-feed search and pinned-only scope on cursor requests", async () => {
  request.mockResolvedValue({ items: [], next_cursor: null });
  const signal = new AbortController().signal;
  await listFeed(uuid, { search: "Đề ôn & notes", pinnedOnly: true, cursor: "next", signal });
  const path = request.mock.calls.at(-1)?.[0] as string, params = new URL(path, "http://test").searchParams;
  expect(params.get("search")).toBe("Đề ôn & notes"); expect(params.get("pinned_only")).toBe("true"); expect(params.get("cursor")).toBe("next");
  expect(request.mock.calls.at(-1)?.[1]).toEqual({ signal });
});
it("parses canonical resource activity and keeps the kind in server pagination filters", async () => {
  const resource = { id: uuid, classroom_id: uuid, title: "Fictional notes", description: null, kind: "TEXT", body: "Fictional lesson", url: null, status: "PUBLISHED", original_filename: null, media_type: null, size_bytes: null, created_at: "now", updated_at: "now" };
  request.mockResolvedValue({ items: [{ id: uuid, kind: "RESOURCE_ACTIVITY", title: resource.title, body: "", status: "PUBLISHED", pinned: false, locked: true, author_id: uuid, author_name: "Fictional tutor", author_role: "TEACHER", created_at: "now", updated_at: "now", published_at: "now", comment_count: 0, resource_ids: [uuid], assignment_id: null, resource, resource_topic: "Fictional topic" }], next_cursor: "next" });
  const result = await listFeed(uuid, { contentKind: "RESOURCE_ACTIVITY" });
  expect(result.items[0].resource).toEqual(resource);
  expect(result.next_cursor).toBe("next");
  expect(request).toHaveBeenCalledWith(`/classrooms/${uuid}/feed?limit=20&content_kind=RESOURCE_ACTIVITY`);
});
it("parses resource mutation responses and uploads through the existing credentialed client", async () => {
  const response = { id: uuid, classroom_id: uuid, title: "Notes", description: null, kind: "TEXT", body: "Lesson", url: null, status: "DRAFT", original_filename: null, media_type: null, size_bytes: null, created_at: "now", updated_at: "now" }; request.mockResolvedValue(response);
  expect(await createResource(uuid, { title: "Notes", kind: "TEXT", body: "Lesson", status: "DRAFT" })).toEqual(response);
  await uploadResource(uuid, { title: "PDF", file: new File(["test"], "lesson.pdf", { type: "application/pdf" }), status: "DRAFT", section_id: null });
  const init = request.mock.calls.at(-1)?.[1]; expect(init.body).toBeInstanceOf(FormData); expect(init.body.get("file").name).toBe("lesson.pdf");
});
it("fetches private files through apiResponse so expired access can refresh", async () => {
  const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" }), signal = new AbortController().signal;
  response.mockResolvedValue({ blob: async () => blob });
  expect(await fetchResourceFile(uuid, uuid, signal)).toBe(blob);
  expect(response).toHaveBeenCalledWith(`/classrooms/${uuid}/resources/${uuid}/file?inline=true`, { signal });
});
