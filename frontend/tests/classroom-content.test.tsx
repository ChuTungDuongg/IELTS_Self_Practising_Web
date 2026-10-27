import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { SafeMarkdown } from "@/features/classrooms/content/safe-markdown";
import { ClassroomWorkspace } from "@/features/classrooms/content/classroom-workspace";
import { ApiError } from "@/lib/api/client";
import { ResourceEditor } from "@/features/classrooms/content/resource-editor";
import { ResourceViewer } from "@/features/classrooms/content/resource-viewer";
import { SectionEditor } from "@/features/classrooms/content/section-editor";
import { PostComments } from "@/features/classrooms/content/post-comments";
import { ClassworkPanel } from "@/features/classrooms/content/classwork-panel";
import { ClassroomStream } from "@/features/classrooms/content/classroom-stream";
import { PostCard } from "@/features/classrooms/content/post-card";

const api = vi.hoisted(() => ({ getClasswork: vi.fn(), listFeed: vi.fn(), createPost: vi.fn(), updatePost: vi.fn(), postAction: vi.fn(), listComments: vi.fn(), createComment: vi.fn(), updateComment: vi.fn(), retractComment: vi.fn(), reorderSections: vi.fn(), reorderItems: vi.fn(), createSection: vi.fn(), updateSection: vi.fn(), createResource: vi.fn(), updateResource: vi.fn(), uploadResource: vi.fn(), placeAssignment: vi.fn(), getPost: vi.fn(), fetchResourceFile: vi.fn() }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), ...api }));
const room = { id: "c", teacher_id: "teacher", name: "Evening classroom", description: "Reading together", status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
const post = { id: "p", kind: "ANNOUNCEMENT" as const, title: "Reading notes", body: "Read **carefully**.", status: "PUBLISHED" as const, pinned: true, locked: false, author_id: "teacher", author_name: "Tutor", author_role: "TEACHER", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", published_at: "2026-10-27T08:00:00Z", comment_count: 0, resource_ids: [], assignment_id: null };
const section = (id: string, title: string, position: number) => ({ id, classroom_id: "c", title, description: null, status: "PUBLISHED" as const, position, created_at: "now", updated_at: "now" });
const resource = { id: "r", classroom_id: "c", title: "Lesson notes", description: null, kind: "TEXT" as const, body: "A useful lesson", url: null, status: "PUBLISHED" as const, original_filename: null, media_type: null, size_bytes: null, created_at: "now", updated_at: "now" };
const classwork = { revision: 3, sections: [section("s1", "Week 1", 0), section("s2", "Week 2", 1)], resources: [resource], items: [{ id: "i", section_id: "s1", resource_id: "r", assignment_id: null, position: 0 }] };
function workspace(role = "USER", status: "ACTIVE" | "ARCHIVED" = "ACTIVE", userId = role === "TEACHER" ? "teacher" : "student") {
  return <ClassroomWorkspace classroom={{ ...room, status }} user={{ id: userId, role }} assignments={[]} people={<p>Membership management retained</p>} assignmentForm={<p>Existing assignment form</p>} canManage={role !== "USER"} />;
}
beforeEach(() => {
  localStorage.clear(); vi.resetAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:private-resource"); URL.revokeObjectURL = vi.fn(); api.fetchResourceFile.mockResolvedValue(new Blob(["image"], { type: "image/png" }));
  api.getClasswork.mockResolvedValue(classwork); api.listFeed.mockResolvedValue({ items: [post], next_cursor: null });
  api.listComments.mockResolvedValue({ items: [], next_cursor: null }); api.createComment.mockResolvedValue({ id: "comment" });
  api.createPost.mockResolvedValue(post); api.updatePost.mockResolvedValue(post); api.postAction.mockResolvedValue(post);
  api.createSection.mockResolvedValue(classwork.sections[0]); api.updateSection.mockResolvedValue(classwork.sections[0]); api.createResource.mockResolvedValue(resource); api.updateResource.mockResolvedValue(resource); api.uploadResource.mockResolvedValue({ ...resource, kind: "FILE" }); api.placeAssignment.mockResolvedValue(classwork);
  api.reorderSections.mockResolvedValue({ ...classwork, revision: 4 }); api.reorderItems.mockResolvedValue({ ...classwork, revision: 4 });
});
it("renders only safe Markdown React nodes and http(s) links", () => {
  const view = renderWithLocale(<SafeMarkdown text={'# Lesson\n\n**Bold** and *emphasis* [safe](https://example.com) [bad](javascript:alert)\n\n<img src=x onerror=alert(1)>\n\n- First\n- Second'} />);
  expect(screen.getByText("Bold").tagName).toBe("STRONG");
  expect(screen.getByRole("link", { name: "safe" })).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.queryByRole("link", { name: "bad" })).not.toBeInTheDocument();
  expect(view.container.querySelector("img")).toBeNull(); expect(screen.getAllByRole("listitem")).toHaveLength(2);
});
it("loads Stream, switches tabs, and preserves the existing people and assignment surfaces", async () => {
  renderWithLocale(workspace("TEACHER"));
  expect(await screen.findByText("Reading notes")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "People" })); expect(screen.getByText("Membership management retained")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Assignments" })); expect(screen.getByText("Existing assignment form")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Classwork" })); expect(await screen.findByRole("heading", { name: "Lesson notes" })).toBeInTheDocument();
});
it("reserves content authoring for the owner teacher and makes archived rooms read-only", async () => {
  const view = renderWithLocale(workspace("ADMIN")); await screen.findByText("Reading notes");
  expect(screen.queryByRole("button", { name: "New post" })).not.toBeInTheDocument();
  view.rerender(workspace("TEACHER", "ACTIVE", "other-teacher"));
  expect(screen.queryByRole("button", { name: "New post" })).not.toBeInTheDocument();
  view.rerender(workspace("TEACHER", "ARCHIVED"));
  expect(screen.queryByRole("button", { name: "New post" })).not.toBeInTheDocument();
  expect(screen.getByText("This classroom is archived. Retained content is available to read.")).toBeInTheDocument();
});
it("validates post body, saves a draft, and localizes new controls", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes");
  fireEvent.click(screen.getByRole("button", { name: "New post" }));
  fireEvent.click(screen.getByRole("button", { name: "Save draft" })); expect(api.createPost).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "  Notes for this week  " } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(api.createPost).toHaveBeenCalledWith("c", expect.objectContaining({ body: "Notes for this week", status: "DRAFT" })));
  fireEvent.click(screen.getByText("Switch to Vietnamese")); expect(screen.getByRole("tab", { name: "Bảng tin" })).toBeInTheDocument();
});
it("creates a comment and requires confirmation before retracting it", async () => {
  api.listComments.mockResolvedValue({ items: [{ id: "comment", post_id: "p", author_id: "student", author_name: "Learner", body: "My question", state: "VISIBLE", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z" }], next_cursor: null });
  renderWithLocale(workspace()); await screen.findByText("Reading notes");
  fireEvent.click(screen.getByRole("button", { name: /Comments/ })); await screen.findByText("My question");
  fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "A new question" } }); fireEvent.click(screen.getByRole("button", { name: "Send comment" }));
  await waitFor(() => expect(api.createComment).toHaveBeenCalledWith("c", "p", "A new question"));
  fireEvent.click(screen.getByRole("button", { name: "Retract" })); expect(api.retractComment).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Retract" }));
  await waitFor(() => expect(api.retractComment).toHaveBeenCalledWith("c", "comment"));
});
it("persists keyboard section reordering with revision and refreshes conflicts", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes"); fireEvent.click(screen.getByRole("tab", { name: "Classwork" }));
  fireEvent.click(screen.getByRole("button", { name: "Move Week 2 up" }));
  await waitFor(() => expect(api.reorderSections).toHaveBeenCalledWith("c", ["s2", "s1"], 3));
  api.reorderSections.mockRejectedValueOnce(new ApiError("CLASSWORK_CHANGED", "Conflict", 409));
  fireEvent.click(screen.getByRole("button", { name: "Move Week 2 up" }));
  expect(await screen.findByText("Classwork changed elsewhere. The latest order has been loaded; try your move again.")).toBeInTheDocument();
  expect(api.getClasswork).toHaveBeenCalledTimes(2);
});
it("moves a resource with the full target order and revision", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes"); fireEvent.click(screen.getByRole("tab", { name: "Classwork" }));
  fireEvent.change(screen.getByLabelText("Move Lesson notes to section"), { target: { value: "s2" } });
  await waitFor(() => expect(api.reorderItems).toHaveBeenCalledWith("c", "s2", ["i"], 3));
});
it("shows retry for failed feed loads and an empty state after recovery", async () => {
  api.listFeed.mockRejectedValueOnce(new Error("offline")); renderWithLocale(workspace());
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load classroom content.");
  api.listFeed.mockResolvedValue({ items: [], next_cursor: null }); fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No classroom updates yet.")).toBeInTheDocument();
});
it("supports keyboard tab navigation and reports a loading frame", async () => {
  let resolve: (value: unknown) => void = () => {}; api.listFeed.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  renderWithLocale(workspace()); expect(screen.getByRole("status")).toHaveTextContent("Loading classroom content");
  fireEvent.keyDown(screen.getByRole("tab", { name: "Stream" }), { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Classwork" })).toHaveAttribute("aria-selected", "true");
  resolve({ items: [], next_cursor: null }); await screen.findByRole("heading", { name: "Lesson notes" });
});
it("publishes and unpins owner posts and confirms archival", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes");
  fireEvent.click(screen.getByRole("button", { name: "Unpin" })); await waitFor(() => expect(api.postAction).toHaveBeenCalledWith("c", "p", "pin", false));
  fireEvent.click(screen.getByRole("button", { name: "Archive" })); expect(api.postAction).not.toHaveBeenCalledWith("c", "p", "archive");
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" })); await waitFor(() => expect(api.postAction).toHaveBeenCalledWith("c", "p", "archive"));
});
it("edits existing post content and attached resource references", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes"); fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Edited notes" } }); fireEvent.click(screen.getByText("Attach learning resources"));
  fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(api.updatePost).toHaveBeenCalledWith("c", "p", expect.objectContaining({ body: "Edited notes", resource_ids: ["r"], status: "PUBLISHED" })));
});
it("creates and edits section metadata through the section API", async () => {
  const done = vi.fn().mockResolvedValue(undefined), cancel = vi.fn();
  const view = renderWithLocale(<SectionEditor classroomId="c" onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Section title"), { target: { value: "  Week 3  " } }); fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  await waitFor(() => expect(api.createSection).toHaveBeenCalledWith("c", { title: "Week 3", description: null, status: "DRAFT" }));
  view.unmount(); renderWithLocale(<SectionEditor classroomId="c" section={classwork.sections[0]} onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Practice reading" } }); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(api.updateSection).toHaveBeenCalledWith("c", "s1", { title: "Week 1", description: "Practice reading" }));
});
it("creates published text resources and validates external URLs", async () => {
  const done = vi.fn().mockResolvedValue(undefined), cancel = vi.fn();
  const view = renderWithLocale(<ResourceEditor classroomId="c" sections={classwork.sections} sectionId="s1" onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: "Reading guide" } }); fireEvent.change(screen.getByLabelText("Lesson content"), { target: { value: "**Read** the guide" } }); fireEvent.click(screen.getByRole("button", { name: "Publish" }));
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith("c", { title: "Reading guide", description: null, kind: "TEXT", body: "**Read** the guide", section_id: "s1", status: "PUBLISHED" }));
  view.unmount(); renderWithLocale(<ResourceEditor classroomId="c" sections={[]} onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: "Website" } }); fireEvent.change(screen.getByLabelText("Resource type"), { target: { value: "LINK" } }); fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "javascript:alert(1)" } }); fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter a complete http:// or https:// website URL."); expect(api.createResource).toHaveBeenCalledTimes(1);
});
it("uploads files and preserves file identity when metadata is edited", async () => {
  const done = vi.fn().mockResolvedValue(undefined), cancel = vi.fn();
  const view = renderWithLocale(<ResourceEditor classroomId="c" sections={[]} onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: "Worksheet" } }); fireEvent.change(screen.getByLabelText("Resource type"), { target: { value: "FILE" } });
  const file = new File(["%PDF-1.4"], "lesson.pdf", { type: "application/pdf" }); fireEvent.change(screen.getByLabelText("Choose file"), { target: { files: [file] } });
  // jsdom does not update native file-input validity from its synthetic FileList.
  fireEvent.submit(screen.getByRole("button", { name: "Save draft" }).closest("form")!);
  await waitFor(() => expect(api.uploadResource).toHaveBeenCalledWith("c", { title: "Worksheet", description: null, status: "DRAFT", section_id: null, file }));
  view.unmount(); renderWithLocale(<ResourceEditor classroomId="c" sections={[]} resource={{ ...resource, kind: "FILE", body: null }} onDone={done} onCancel={cancel} />);
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: "Renamed worksheet" } }); fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(api.updateResource).toHaveBeenCalledWith("c", "r", { title: "Renamed worksheet", description: null, status: "PUBLISHED" }));
});
it("loads private images through the refresh-aware client and releases preview URLs", async () => {
  renderWithLocale(<ResourceViewer resource={{ ...resource, kind: "FILE", body: null, original_filename: "diagram.png", media_type: "image/png", size_bytes: 1024 }} />);
  fireEvent.click(screen.getByRole("button", { name: "Read resource" }));
  expect(await screen.findByRole("img", { name: "Lesson notes" })).toHaveAttribute("src", "blob:private-resource");
  expect(api.fetchResourceFile).toHaveBeenCalledWith("c", "r", expect.any(AbortSignal));
  expect(screen.getByRole("link", { name: "Download file" })).toHaveAttribute("download", "diagram.png");
  fireEvent.click(screen.getByRole("button", { name: "Close resource" })); expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:private-resource");
});
it("allows owner moderation on locked posts while blocking new comments", async () => {
  api.listComments.mockResolvedValue({ items: [{ id: "comment", post_id: "p", author_id: "student", author_name: "Learner", body: "A question", state: "VISIBLE", created_at: "now", updated_at: "now" }], next_cursor: null });
  renderWithLocale(<PostComments classroomId="c" postId="p" userId="teacher" canModerate readOnly={false} locked onCountChange={() => {}} />);
  await screen.findByText("A question"); expect(screen.queryByLabelText("Your comment")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove comment" })); fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove comment" }));
  await waitFor(() => expect(api.retractComment).toHaveBeenCalledWith("c", "comment"));
});
it("associates canonical assignments without creating a duplicate assignment", async () => {
  const assignment = { id: "a", classroom_id: "c", test_version_id: "v", created_by_user_id: "teacher", title: "Existing reading", note: null, status: "ACTIVE" as const, created_at: "now", archived_at: null };
  renderWithLocale(<ClassworkPanel classroomId="c" data={classwork} assignments={[assignment]} canAuthor onRefresh={vi.fn()} onChange={vi.fn()} onOpenAssignment={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Choose an assignment"), { target: { value: "a" } }); fireEvent.change(screen.getByLabelText("Section"), { target: { value: "s1" } }); fireEvent.click(screen.getByRole("button", { name: "Add existing assignment" }));
  await waitFor(() => expect(api.placeAssignment).toHaveBeenCalledWith("c", "s1", "a"));
});
it("persists native drag-and-drop moves using the same revision contract", async () => {
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes"); fireEvent.click(screen.getByRole("tab", { name: "Classwork" }));
  const transfer = { effectAllowed: "", setData: vi.fn(), dropEffect: "" };
  fireEvent.dragStart(screen.getByRole("button", { name: "Drag to move learning material: Lesson notes" }), { dataTransfer: transfer });
  fireEvent.drop(screen.getByRole("region", { name: "Week 2" }), { dataTransfer: transfer });
  await waitFor(() => expect(api.reorderItems).toHaveBeenCalledWith("c", "s2", ["i"], 3));
});
it("reacts to notification navigation between posts in the same classroom", async () => {
  api.listFeed.mockResolvedValue({ items: [], next_cursor: null }); api.getPost.mockImplementation(async (_room, id) => ({ ...post, id, title: id === "post-a" ? "First announcement" : "Next announcement" }));
  const props = { classroomId: "c", resources: [], userId: "student", canAuthor: false, canInspect: false, archived: false, admin: false, onOpenAssignment: vi.fn() };
  const view = renderWithLocale(<ClassroomStream {...props} selectedPostId="post-a" />); await screen.findByText("First announcement");
  view.rerender(<ClassroomStream {...props} selectedPostId="post-b" />);
  expect(await screen.findByText("Next announcement")).toBeInTheDocument(); expect(screen.queryByText("First announcement")).not.toBeInTheDocument();
  expect(api.getPost).toHaveBeenLastCalledWith("c", "post-b", expect.any(AbortSignal));
});
it("closes an existing post editor when the classroom becomes archived", () => {
  const props = { classroomId: "c", post, resources: [], userId: "teacher", canAuthor: true, archived: false, admin: false, onRefresh: vi.fn(), onOpenAssignment: vi.fn() };
  const view = renderWithLocale(<PostCard {...props} />); fireEvent.click(screen.getByRole("button", { name: "Edit" })); expect(screen.getByLabelText("Message")).toBeInTheDocument();
  view.rerender(<PostCard {...props} archived />); expect(screen.queryByLabelText("Message")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
});
it("shows creation time and an edited indicator independently of publication time", () => {
  renderWithLocale(<PostCard classroomId="c" post={{ ...post, created_at: "2026-10-20T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", published_at: "2026-10-26T08:00:00Z" }} resources={[]} userId="student" canAuthor={false} archived={false} admin={false} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} />);
  expect(screen.getByText(/Oct 20, 2026.*Edited/)).toBeInTheDocument(); expect(screen.queryByText(/Oct 26, 2026/)).not.toBeInTheDocument();
});
it("offers a retry when private file loading fails without exposing raw API URLs", async () => {
  api.fetchResourceFile.mockRejectedValueOnce(new ApiError("NETWORK_ERROR", "Offline", 0));
  renderWithLocale(<ResourceViewer resource={{ ...resource, kind: "FILE", body: null, original_filename: "notes.pdf", media_type: "application/pdf" }} />);
  fireEvent.click(screen.getByRole("button", { name: "Read resource" })); expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
  expect(screen.queryByRole("link", { name: "Download file" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" })); expect(await screen.findByRole("link", { name: "Download file" })).toHaveAttribute("href", "blob:private-resource");
});
it("reports archived conflicts without pretending the order needs to be retried", async () => {
  api.reorderSections.mockRejectedValueOnce(new ApiError("CLASSROOM_ARCHIVED", "Classroom is archived.", 409));
  renderWithLocale(workspace("TEACHER")); await screen.findByText("Reading notes"); fireEvent.click(screen.getByRole("tab", { name: "Classwork" })); fireEvent.click(screen.getByRole("button", { name: "Move Week 2 up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Classroom is archived."); expect(api.getClasswork).toHaveBeenCalledTimes(1);
});
