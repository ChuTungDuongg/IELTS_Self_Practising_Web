import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ClassroomStream } from "@/features/classrooms/content/classroom-stream";
import { ClassroomWorkspace } from "@/features/classrooms/content/classroom-workspace";
import { AssignmentProgressProvider } from "@/features/classrooms/scheduling/progress-provider";
import { upcomingAssignments, sharedResourceCount } from "@/features/classrooms/content/stream/sidebar-data";
import type { ClassroomPost, Classwork } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import type { AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ listFeed: vi.fn(), getPost: vi.fn(), createPost: vi.fn(), updatePost: vi.fn(), listComments: vi.fn(), createComment: vi.fn(), createResource: vi.fn(), uploadResource: vi.fn(), getClasswork: vi.fn(), getAssignmentProgress: vi.fn(), listMembers: vi.fn() }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), ...api }));
vi.mock("@/lib/api/assignment-scheduling", async original => ({ ...await original<object>(), getAssignmentProgress: api.getAssignmentProgress }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), listMembers: api.listMembers }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const room = { id: "room", teacher_id: "teacher", teacher_name: "Fictional Tutor", active_member_count: 7, name: "Fictional class", description: null, status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
const post: ClassroomPost = { id: "notice", kind: "ANNOUNCEMENT", title: "Welcome to the workshop", body: "Read **these notes**.", status: "PUBLISHED", pinned: true, locked: false, author_id: "teacher", author_name: "Fictional Tutor", author_role: "TEACHER", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", published_at: "2026-10-27T08:00:00Z", comment_count: 4, resource_ids: [], assignment_id: null };
const resource = { id: "resource", classroom_id: "room", title: "Fictional guide", description: "Use these notes", kind: "LINK" as const, body: null, url: "https://example.com/lesson", status: "PUBLISHED" as const, original_filename: null, media_type: null, size_bytes: null, created_at: "now", updated_at: "now" };
const work: Classwork = { revision: 1, sections: [], resources: [resource], items: [{ id: "placed", section_id: null, resource_id: "resource", assignment_id: null, position: 0 }] };
const assignment: ClassroomAssignment = { id: "assignment", classroom_id: "room", test_version_id: "version", created_by_user_id: "teacher", title: "Focused fictional writing", note: null, status: "ACTIVE", created_at: "2026-10-27T08:00:00Z", archived_at: null, due_at: "2026-11-01T09:00:00Z", cutoff_at: "2026-11-02T09:00:00Z", target: { mode: "MODULE", module: "WRITING", scope: "FULL_MODULE" } };
const progress: AssignmentProgress = { assignment_id: assignment.id, availability_status: "OPEN", submission_status: "NOT_STARTED", available_from: null, effective_due_at: "2026-11-03T09:00:00Z", effective_cutoff_at: "2026-11-04T09:00:00Z", max_attempts: 2, attempts_used: 0, attempts_remaining: 2, can_start: true, start_blocked_reason: null, can_resume: false, latest_attempt_id: null, latest_session_id: null, resume_attempt_id: null, resume_session_id: null, result_attempt_id: null, completed_at: null, late: false, accepted: false, historical: false };
const base = { classroomId: "room", resources: [resource], userId: "teacher", userName: "Fictional Tutor", canAuthor: true, canInspect: true, archived: false, admin: false, onOpenAssignment: vi.fn() };
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); api.listFeed.mockResolvedValue({ items: [post], next_cursor: null }); api.createPost.mockResolvedValue(post); api.createResource.mockResolvedValue(resource); api.uploadResource.mockResolvedValue(resource); api.listComments.mockResolvedValue({ items: [], next_cursor: null }); api.getClasswork.mockResolvedValue(work); api.getAssignmentProgress.mockResolvedValue({ items: [progress], total: 1 }); });
afterEach(() => vi.useRealTimers());

it("renders real author, pinned badge and lazy comment counts without fake reactions", async () => {
  const { container } = renderWithLocale(<ClassroomStream {...base} />);
  const article = (await screen.findByRole("heading", { name: post.title! })).closest("article")!;
  expect(within(article).getAllByText("Fictional Tutor")).toHaveLength(1);
  expect(within(article).getByText("Pinned")).toBeInTheDocument();
  expect(article.querySelector("time")).toHaveAttribute("datetime", post.created_at);
  expect(api.listComments).not.toHaveBeenCalled();
  expect(container.querySelector("[data-reaction]")).toBeNull();
  expect(screen.queryByRole("button", { name: /like|heart/i })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Comments (4)" }));
  await waitFor(() => expect(api.listComments).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Comments (4)" }));
  expect(screen.queryByLabelText("Your comment")).not.toBeInTheDocument();
});

it.each([ ["Announcement", "ANNOUNCEMENT"], ["Discussion", "DISCUSSION"], ["Assignments", "ASSIGNMENT_ACTIVITY"], ["Resource", "RESOURCE_ACTIVITY"] ])("filters %s through the bounded server query", async (label, kind) => {
  renderWithLocale(<ClassroomStream {...base} />); await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: label }));
  await waitFor(() => expect(api.listFeed).toHaveBeenLastCalledWith("room", expect.objectContaining({ contentKind: kind })));
  expect(api.listFeed.mock.calls.at(-1)?.[1].cursor).toBeUndefined();
});

it("paginates without duplicate identities and binds pinned-only search to every page", async () => {
  api.listFeed.mockResolvedValue({ items: [post], next_cursor: "next" });
  renderWithLocale(<ClassroomStream {...base} />); await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: "Pinned" }));
  await waitFor(() => expect(api.listFeed.mock.calls.at(-1)?.[1].pinnedOnly).toBe(true));
  fireEvent.change(screen.getByRole("searchbox", { name: "Search the newsfeed" }), { target: { value: "Đề ôn" } });
  await waitFor(() => expect(api.listFeed.mock.calls.at(-1)?.[1].search).toBe("Đề ôn"));
  api.listFeed.mockResolvedValue({ items: [post, { ...post, id: "second", title: "Second notice" }], next_cursor: null });
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  await screen.findByRole("heading", { name: "Second notice" });
  expect(api.listFeed).toHaveBeenLastCalledWith("room", expect.objectContaining({ search: "Đề ôn", pinnedOnly: true, cursor: "next" }));
  expect(screen.getAllByRole("article")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Clear feed search" }));
  await waitFor(() => expect(api.listFeed.mock.calls.at(-1)?.[1].search).toBeUndefined());
  expect(api.listFeed.mock.calls.at(-1)?.[1].cursor).toBeUndefined();
});

it("aborts stale filter requests and ignores late responses", async () => {
  let finish!: (value: unknown) => void;
  api.listFeed.mockReturnValueOnce(new Promise(resolve => { finish = resolve; })).mockResolvedValue({ items: [{ ...post, id: "discussion", title: "New discussion", kind: "DISCUSSION" }], next_cursor: null });
  renderWithLocale(<ClassroomStream {...base} />);
  await waitFor(() => expect(api.listFeed).toHaveBeenCalledOnce());
  const signal = api.listFeed.mock.calls[0][1].signal as AbortSignal;
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: "Discussion" }));
  await screen.findByRole("heading", { name: "New discussion" });
  await act(async () => finish({ items: [post], next_cursor: null }));
  expect(signal.aborted).toBe(true); expect(screen.queryByRole("heading", { name: post.title! })).not.toBeInTheDocument();
});

it.each([ ["Announcement", "ANNOUNCEMENT"], ["Discussion", "DISCUSSION"] ])("opens a compact %s composer and publishes through the real post contract", async (label, kind) => {
  renderWithLocale(<ClassroomStream {...base} />); await screen.findByRole("heading", { name: post.title! });
  const composer = screen.getByRole("region", { name: "New post" });
  expect(within(composer).queryByLabelText("Message")).not.toBeInTheDocument();
  fireEvent.click(within(composer).getByRole("button", { name: label }));
  expect(screen.getByLabelText("Post type")).toHaveValue(kind);
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "  Fictional new update  " } });
  fireEvent.click(within(screen.getByRole("form", { name: "New post" })).getByRole("button", { name: "Publish" }));
  await waitFor(() => expect(api.createPost).toHaveBeenCalledWith("room", expect.objectContaining({ kind, body: "Fictional new update", status: "PUBLISHED" })));
  await waitFor(() => expect(screen.queryByLabelText("Message")).not.toBeInTheDocument());
  expect(api.listFeed).toHaveBeenCalledTimes(2);
});

it("does not resubmit a saved draft when refreshing fails", async () => {
  api.listFeed.mockResolvedValueOnce({ items: [post], next_cursor: null }).mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ items: [post], next_cursor: null });
  renderWithLocale(<ClassroomStream {...base} />); await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(screen.getByRole("button", { name: "New post" }));
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "A draft" } });
  const form = screen.getByRole("form", { name: "New post" });
  fireEvent.submit(form); fireEvent.submit(form);
  await screen.findByText(/Saved, but this view/);
  expect(api.createPost).toHaveBeenCalledOnce();
  expect(api.createPost.mock.calls[0][1].status).toBe("DRAFT");
  fireEvent.submit(form); expect(api.createPost).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Retry loading" }));
  await waitFor(() => expect(screen.queryByLabelText("Message")).not.toBeInTheDocument());
  expect(api.createPost).toHaveBeenCalledOnce();
});

it("reuses the LINK resource editor and canonical activity without creating a second post", async () => {
  const changed = vi.fn().mockResolvedValue(undefined);
  renderWithLocale(<ClassroomStream {...base} classwork={work} onResourcesChanged={changed} />); await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(within(screen.getByRole("region", { name: "New post" })).getByRole("button", { name: "Link" }));
  expect(screen.getByLabelText("Resource type")).toHaveValue("LINK");
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: resource.title } });
  fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: resource.url } });
  api.listFeed.mockResolvedValue({ items: [{ ...post, id: resource.id, kind: "RESOURCE_ACTIVITY", pinned: false, title: resource.title, resource, resource_ids: [resource.id] }], next_cursor: null });
  fireEvent.click(within(screen.getByRole("form", { name: "Add resource" })).getByRole("button", { name: "Publish" }));
  await waitFor(() => expect(api.createResource).toHaveBeenCalledWith("room", expect.objectContaining({ kind: "LINK", status: "PUBLISHED", url: resource.url })));
  await screen.findByRole("heading", { name: resource.title });
  expect(changed).toHaveBeenCalledOnce(); expect(api.createPost).not.toHaveBeenCalled(); expect(screen.getAllByRole("article")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Read resource" }));
  expect(screen.getByRole("link", { name: "Open website" })).toHaveAttribute("rel", "noopener noreferrer");
});

it("preselects actual file upload and preserves unsaved editor and feed across locale changes", async () => {
  renderWithLocale(<ClassroomStream {...base} />); await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(within(screen.getByRole("region", { name: "New post" })).getByRole("button", { name: "Resource" }));
  expect(screen.getByLabelText("Resource type")).toHaveValue("FILE"); expect(screen.getByLabelText("Choose file")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Resource title"), { target: { value: "Unsaved guide" } });
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByDisplayValue("Unsaved guide")).toBeInTheDocument(); expect(screen.getByRole("searchbox", { name: "Tìm trong bảng tin" })).toBeInTheDocument();
  expect(api.listFeed).toHaveBeenCalledOnce();
});

it("keeps Admin read-only even when stale authoring flags are supplied", async () => {
  renderWithLocale(<ClassroomStream {...base} admin canModerate />); await screen.findByRole("heading", { name: post.title! });
  expect(screen.queryByRole("region", { name: "New post" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Edit|Publish|Unpin|Archive|Delete/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Comments (4)" }));
  await waitFor(() => expect(api.listComments).toHaveBeenCalledOnce());
  expect(screen.queryByLabelText("Your comment")).not.toBeInTheDocument();
});

it("uses actual class metrics and authorized roster without per-metric or roster fetches", async () => {
  renderWithLocale(<ClassroomStream {...base} classroom={room} assignments={[assignment]} classwork={work} members={[{ user_id: "learner", display_name: "Fictional Mina" }]} canViewRoster onNavigate={vi.fn()} />);
  await screen.findByRole("heading", { name: post.title! });
  const metrics = screen.getByRole("region", { name: "Classroom overview" });
  expect(within(metrics).getByText("Students").nextElementSibling).toHaveTextContent("7");
  expect(within(metrics).getByText("Active assignments").nextElementSibling).toHaveTextContent("1");
  expect(within(metrics).getByText("Shared resources").nextElementSibling).toHaveTextContent("1");
  expect(screen.getByText("Fictional Mina")).toBeInTheDocument(); expect(api.listMembers).not.toHaveBeenCalled(); expect(api.listFeed).toHaveBeenCalledOnce();
});

it("uses effective student deadlines and never exposes an unauthorized roster", async () => {
  vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date("2026-10-28T00:00:00Z"));
  renderWithLocale(<AssignmentProgressProvider classroomId="room" ids={[assignment.id]} assignments={[assignment]}><ClassroomStream {...base} canAuthor={false} canInspect={false} student classroom={room} assignments={[assignment]} classwork={work} onNavigate={vi.fn()} /></AssignmentProgressProvider>);
  const upcoming = screen.getByRole("region", { name: "Upcoming deadlines" });
  await waitFor(() => expect(upcoming.querySelector("time")).toHaveAttribute("datetime", progress.effective_due_at));
  expect(screen.getByText(/full roster is restricted/)).toBeInTheDocument();
  expect(api.listMembers).not.toHaveBeenCalled(); expect(screen.queryByRole("button", { name: "New post" })).not.toBeInTheDocument();
  fireEvent.click(within(upcoming).getByRole("button", { name: /Focused fictional writing/ }));
  expect(base.onOpenAssignment).toHaveBeenCalledWith(assignment.id);
});

it("sorts future deadlines, distinguishes cut-off, and excludes archived, undated and completed work", () => {
  const now = Date.parse("2026-10-28T00:00:00Z");
  const entries = [assignment, { ...assignment, id: "early", due_at: "2026-10-29T00:00:00Z" }, { ...assignment, id: "archived", status: "ARCHIVED" as const }, { ...assignment, id: "undated", due_at: null, cutoff_at: null }, { ...assignment, id: "cutoff", due_at: "2026-10-27T00:00:00Z", cutoff_at: "2026-10-30T00:00:00Z" }];
  const upcoming = upcomingAssignments(entries, {}, false, now);
  expect(upcoming.map(item => item.assignment.id)).toEqual(["early", "cutoff", "assignment"]);
  expect(upcoming[1].kind).toBe("cutoff");
  expect(upcomingAssignments([assignment], { [assignment.id]: { ...progress, completed_at: "2026-10-27T12:00:00Z" } }, true, now)).toEqual([]);
  expect(sharedResourceCount({ ...work, resources: [resource, { ...resource, id: "draft", status: "DRAFT" }] })).toBe(1);
});

it("retains the same feed and composer when switching Classroom tabs and handles header creation", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={room} user={{ id: "teacher", role: "TEACHER", display_name: "Fictional Tutor" }} assignments={[]} />);
  await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(screen.getByRole("button", { name: "New post" }));
  fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Keep these notes" } });
  fireEvent.click(screen.getByRole("tab", { name: "Classwork" }));
  fireEvent.click(screen.getByRole("tab", { name: "Stream" }));
  expect(screen.getByLabelText("Message")).toHaveValue("Keep these notes"); expect(api.listFeed).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  const headerMenu = document.querySelector(".classroom-header-actions details")!;
  fireEvent.click(headerMenu.querySelector("summary")!);
  fireEvent.click(within(headerMenu as HTMLElement).getByRole("button", { name: /announcement/i }));
  await screen.findByLabelText("Message");
  await waitFor(() => expect(screen.getByLabelText("Title (optional)")).toHaveFocus());
  expect(screen.getAllByRole("form", { name: "New post" })).toHaveLength(1); expect(api.listFeed).toHaveBeenCalledOnce();
});

it("renders canonical assignment target, schedule and navigation without student start controls or full progress panels", async () => {
  api.listFeed.mockResolvedValue({ items: [{ ...post, id: assignment.id, kind: "ASSIGNMENT_ACTIVITY", title: null, body: "Practice the assigned writing module.", assignment_id: assignment.id, pinned: false }], next_cursor: null });
  renderWithLocale(<AssignmentProgressProvider classroomId="room" ids={[assignment.id]} assignments={[assignment]} staff><ClassroomStream {...base} /></AssignmentProgressProvider>);
  await screen.findByRole("heading", { name: assignment.title! });
  expect(screen.getByText("Writing · Full module")).toBeInTheDocument();
  expect(document.querySelector(`time[datetime="${assignment.cutoff_at}"]`)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Open assignment" })); expect(base.onOpenAssignment).toHaveBeenCalledWith(assignment.id);
  expect(screen.queryByRole("button", { name: "Start assignment" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Starts used/)).not.toBeInTheDocument(); expect(api.getAssignmentProgress).not.toHaveBeenCalled(); expect(api.listComments).not.toHaveBeenCalled();
});

it("keeps empty and unavailable sidebar sections honest and allows resetting the filtered feed", async () => {
  api.listFeed.mockResolvedValue({ items: [], next_cursor: null });
  renderWithLocale(<ClassroomStream {...base} classroom={{ ...room, active_member_count: null }} assignments={[]} classworkError canViewRoster onNavigate={vi.fn()} />);
  await screen.findByText("No classroom updates yet.");
  expect(screen.getByText("No activity in this view.")).toBeInTheDocument();
  expect(screen.getByText("No upcoming assignment deadlines.")).toBeInTheDocument();
  expect(screen.getByText("Roster preview is unavailable.")).toBeInTheDocument(); expect(screen.getByText("Shared resources are unavailable.")).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: "Pinned" }));
  await screen.findByText("No updates match these filters or search.");
  fireEvent.click(within(screen.getByRole("region", { name: "Recent activity" })).getByRole("button", { name: "View all" }));
  await screen.findByText("No classroom updates yet."); expect(api.listFeed.mock.calls.at(-1)?.[1].pinnedOnly).toBeUndefined();
});

it("does not reinsert a late deep-linked announcement after the user filters the feed", async () => {
  let finish!: (value: unknown) => void;
  api.getPost.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  api.listFeed.mockResolvedValue({ items: [], next_cursor: null });
  renderWithLocale(<ClassroomStream {...base} selectedPostId="notice" />);
  await screen.findByText("No classroom updates yet.");
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: "Discussion" }));
  await screen.findByText("No updates match these filters or search.");
  await act(async () => finish(post));
  expect(screen.queryByRole("heading", { name: post.title! })).not.toBeInTheDocument();
});

it("refreshes the authoritative comment count without resetting loaded feed pages", async () => {
  api.listFeed.mockResolvedValueOnce({ items: [post], next_cursor: "next" }).mockResolvedValue({ items: [{ ...post, id: "second", title: "Second page notice" }], next_cursor: null });
  api.createComment.mockResolvedValue({}); api.getPost.mockResolvedValue({ ...post, comment_count: 5 });
  renderWithLocale(<ClassroomStream {...base} />);
  await screen.findByRole("heading", { name: post.title! });
  fireEvent.click(screen.getByRole("button", { name: "Load more" })); await screen.findByRole("heading", { name: "Second page notice" });
  fireEvent.click(within(screen.getByRole("heading", { name: post.title! }).closest("article")!).getByRole("button", { name: "Comments (4)" }));
  await screen.findByLabelText("Your comment");
  fireEvent.change(screen.getByLabelText("Your comment"), { target: { value: "A fictional question" } });
  fireEvent.click(screen.getByRole("button", { name: "Send comment" }));
  await screen.findByRole("button", { name: "Comments (5)" });
  expect(api.getPost).toHaveBeenCalledExactlyOnceWith("room", "notice"); expect(api.listFeed).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("heading", { name: "Second page notice" })).toBeInTheDocument();
});

it("invalidates a retained feed after work changes in another tab, without polling or duplicate initial reads", async () => {
  const view = renderWithLocale(<ClassroomStream {...base} classwork={work} active />);
  await screen.findByRole("heading", { name: post.title! }); expect(api.listFeed).toHaveBeenCalledOnce();
  view.rerender(<ClassroomStream {...base} classwork={work} active={false} />);
  view.rerender(<ClassroomStream {...base} classwork={{ ...work, revision: 2 }} active={false} />);
  expect(api.listFeed).toHaveBeenCalledOnce();
  view.rerender(<ClassroomStream {...base} classwork={{ ...work, revision: 2 }} active />);
  await waitFor(() => expect(api.listFeed).toHaveBeenCalledTimes(2));
  view.rerender(<ClassroomStream {...base} classwork={{ ...work, revision: 2 }} active />);
  expect(api.listFeed).toHaveBeenCalledTimes(2);
});
