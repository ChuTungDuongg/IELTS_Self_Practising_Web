import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { PostCard } from "@/features/classrooms/content/post-card";
import { ClassworkPanel } from "@/features/classrooms/content/classwork-panel";
import { classworkGroups } from "@/features/classrooms/content/classwork-groups";

const api = vi.hoisted(() => ({ deletePost: vi.fn(), deleteResource: vi.fn(), deleteSection: vi.fn(), removeAssignmentItem: vi.fn() }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), ...api }));
const resource = { id: "r", classroom_id: "c", title: "Fictional resource", description: null, kind: "TEXT" as const, body: "Fictional learning notes", url: null, status: "PUBLISHED" as const, original_filename: null, media_type: null, size_bytes: null, created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z" };
const topic = { id: "s", classroom_id: "c", title: "Fictional topic", description: null, status: "PUBLISHED" as const, position: 0, created_at: "now", updated_at: "now" };
const data = { revision: 3, sections: [topic], resources: [resource], items: [{ id: "i", section_id: "s", resource_id: "r", assignment_id: null, position: 0 }] };
const post = { id: "p", kind: "ANNOUNCEMENT" as const, title: "Fictional notice", body: "Fictional update", status: "PUBLISHED" as const, pinned: false, locked: false, author_id: "teacher", author_name: "Tutor", author_role: "TEACHER", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", published_at: "2026-10-27T08:00:00Z", comment_count: 0, resource_ids: [], assignment_id: null };
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); api.deleteResource.mockResolvedValue({ ...data, resources: [], items: [] }); api.deleteSection.mockResolvedValue({ ...data, sections: [] }); });
it("requires confirmation before deleting a post and preserves the existing refresh workflow", async () => {
  const refresh = vi.fn(); renderWithLocale(<PostCard classroomId="c" post={post} resources={[]} userId="teacher" canAuthor archived={false} admin={false} onRefresh={refresh} onOpenAssignment={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete" })); expect(api.deletePost).not.toHaveBeenCalled();
  expect(screen.getByRole("dialog")).toHaveTextContent("Comments and notification history are retained"); fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(api.deletePost).toHaveBeenCalledWith("c", "p")); expect(refresh).toHaveBeenCalledOnce();
});
it("deletes a resource through revision-aware contextual confirmation", async () => {
  const change = vi.fn(); renderWithLocale(<ClassworkPanel classroomId="c" data={data} assignments={[]} canAuthor onChange={change} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} />);
  const row = screen.getByText("Fictional resource").closest("li")!;
  fireEvent.click(within(row).getByRole("button", { name: "Delete" })); expect(api.deleteResource).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" })); await waitFor(() => expect(api.deleteResource).toHaveBeenCalledWith("c", "r", 3)); expect(change).toHaveBeenCalledOnce();
});
it("shows the topic deletion consequence and keeps student delete controls absent", () => {
  const view = renderWithLocale(<ClassworkPanel classroomId="c" data={data} assignments={[]} canAuthor onChange={vi.fn()} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} />);
  const region = screen.getByRole("region", { name: "Fictional topic" }); fireEvent.click(within(region.querySelector("header")!).getByRole("button", { name: "Delete" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Resources, assignments and student work are preserved");
  view.rerender(<ClassworkPanel classroomId="c" data={data} assignments={[]} canAuthor={false} onChange={vi.fn()} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} />); expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
});
it("renders canonical resource activities with the existing authenticated reader and no post comments", () => {
  renderWithLocale(<PostCard classroomId="c" post={{ ...post, id: "r", kind: "RESOURCE_ACTIVITY", title: resource.title, resource_ids: ["r"], resource, resource_topic: "Fictional topic" }} resources={[]} userId="student" canAuthor={false} archived={false} admin={false} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} />);
  expect(screen.getByText("Learning resource")).toBeInTheDocument(); expect(screen.getAllByText(resource.title)).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Read resource" })); expect(screen.getByText(resource.body)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: /Comments/ })).not.toBeInTheDocument();
});
it("does not reintroduce removed canonical assignments as unplaced work", () => {
  const assignment = { id: "a", classroom_id: "c", test_version_id: "v", created_by_user_id: "teacher", title: "Fictional homework", note: null, status: "ACTIVE" as const, created_at: "now", archived_at: null };
  const groups = classworkGroups({ ...data, removed_assignment_ids: ["a"] }, [assignment], false);
  expect(groups.some(group => group.rows.some(row => row.assignment?.id === "a"))).toBe(false);
});
