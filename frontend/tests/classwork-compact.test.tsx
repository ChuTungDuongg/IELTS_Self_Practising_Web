import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { ClassworkPanel } from "@/features/classrooms/content/classwork-panel";
import type { Classwork, ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { progressSchema, type AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { ApiError } from "@/lib/api/client";
import { renderWithLocale } from "./locale-test-utils";
import { ArchivedAssignmentActions } from "@/features/classrooms/content/archived-assignment-actions";

const api = vi.hoisted(() => ({ reorderSections: vi.fn(), reorderItems: vi.fn(), placeAssignment: vi.fn(), updateSection: vi.fn(), updateResource: vi.fn(), removeAssignmentReference: vi.fn() }));
const assignmentsApi = vi.hoisted(() => ({ restoreAssignment: vi.fn(), deleteAssignment: vi.fn() }));
const progress = vi.hoisted(() => ({ items: {} as Record<string, AssignmentProgress>, staff: false, loading: false, error: false, refresh: vi.fn(), assignments: [] as ClassroomAssignment[] }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), ...api }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), ...assignmentsApi }));
vi.mock("@/features/classrooms/scheduling/progress-provider", async original => ({ ...await original<object>(), useAssignmentProgress: () => progress }));

const section = (id: string, position: number): ClassroomSection => ({ id, title: `Topic ${id}`, position, classroom_id: "room", description: null, status: "PUBLISHED", created_at: "now", updated_at: "now" });
const assignment = (id: string, status: "ACTIVE" | "ARCHIVED" = "ACTIVE"): ClassroomAssignment => ({ id, title: `Fictional practice ${id}`, status, classroom_id: "room", test_version_id: "version", created_by_user_id: "owner", note: null, created_at: "now", archived_at: status === "ARCHIVED" ? "now" : null, due_at: null });
const assignments = [assignment("a"), assignment("b"), assignment("u"), assignment("old", "ARCHIVED"), assignment("older", "ARCHIVED")];
const data: Classwork = {
  revision: 7, sections: [section("empty", 0), section("reading", 1), section("writing", 2)],
  resources: [{ id: "notes", title: "Fictional strategy notes", classroom_id: "room", kind: "TEXT", status: "PUBLISHED", body: "Read the fictional notes.", description: null, url: null, original_filename: null, media_type: null, size_bytes: null, created_at: "now", updated_at: "now" }],
  items: [
    { id: "r1", section_id: "reading", resource_id: "notes", assignment_id: null, position: 0 },
    { id: "i1", section_id: "reading", resource_id: null, assignment_id: "a", position: 1 },
    { id: "i2", section_id: "writing", resource_id: null, assignment_id: "b", position: 0 },
    { id: "i3", section_id: "reading", resource_id: null, assignment_id: "old", position: 2 },
  ],
};
function props(extra: Partial<ComponentProps<typeof ClassworkPanel>> = {}) {
  return { classroomId: "room", data, assignments, canAuthor: false, onRefresh: vi.fn().mockResolvedValue(undefined), onChange: vi.fn(), onOpenAssignment: vi.fn(), ...extra };
}
function panel(extra: Partial<ComponentProps<typeof ClassworkPanel>> = {}) { return renderWithLocale(<ClassworkPanel {...props(extra)} />); }
function group(name: string) { return screen.getByRole("region", { name }); }
function toggle(name: string) { return within(group(name)).getByRole("button", { name: new RegExp(`^${name}`) }); }
function state(values: Partial<AssignmentProgress> = {}): AssignmentProgress {
  return progressSchema.parse({ assignment_id: "11111111-1111-4111-8111-111111111111", availability_status: "OPEN", submission_status: "NOT_STARTED", available_from: null, effective_due_at: null, effective_cutoff_at: null, max_attempts: null, attempts_used: 0, attempts_remaining: null, can_start: true, start_blocked_reason: null, can_resume: false, latest_attempt_id: null, latest_session_id: null, resume_attempt_id: null, resume_session_id: null, result_attempt_id: null, completed_at: null, late: false, accepted: false, historical: false, ...values });
}
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); window.history.replaceState(null, "", "/");
  Object.assign(progress, { items: {}, staff: false, loading: false, error: false, assignments });
  api.reorderItems.mockResolvedValue(data); api.reorderSections.mockResolvedValue(data); api.placeAssignment.mockResolvedValue(data);
  api.removeAssignmentReference.mockResolvedValue(data); api.updateResource.mockResolvedValue(data.resources[0]);
  assignmentsApi.restoreAssignment.mockResolvedValue(assignment("old")); assignmentsApi.deleteAssignment.mockResolvedValue(undefined);
});

it("confirms expired restoration without silently editing the schedule or losing target data", async () => {
  const onChanged = vi.fn().mockResolvedValue(undefined), old = { ...assignment("old", "ARCHIVED"), due_at: "2000-01-01T00:00:00Z", cutoff_at: "2000-01-02T00:00:00Z" };
  renderWithLocale(<ArchivedAssignmentActions assignment={old} onChanged={onChanged} />);
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  const dialog = screen.getByRole("dialog", { name: "Restore this assignment?" });
  expect(dialog).toHaveTextContent("cut-off has already passed");
  expect(assignmentsApi.restoreAssignment).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(assignmentsApi.restoreAssignment).toHaveBeenCalledExactlyOnceWith("room", "old");
  expect(old.due_at).toBe("2000-01-01T00:00:00Z");
});

it("confirms permanent deletion includes student attempts and scores without a protected-history detour", async () => {
  const onChanged = vi.fn().mockResolvedValue(undefined);
  renderWithLocale(<ArchivedAssignmentActions assignment={assignment("old", "ARCHIVED")} onChanged={onChanged} />);
  fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveTextContent("all student attempts, scores");
  expect(dialog).toHaveTextContent("cannot be undone");
  expect(assignmentsApi.deleteAssignment).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete permanently" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  expect(api.removeAssignmentReference).not.toHaveBeenCalled();
  expect(assignmentsApi.deleteAssignment).toHaveBeenCalledExactlyOnceWith("room", "old");
});

it("guards duplicate restore requests and retries synchronization without repeating a saved mutation", async () => {
  let resolve!: () => void;
  assignmentsApi.restoreAssignment.mockReturnValue(new Promise<void>(done => { resolve = done; }));
  const onChanged = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  renderWithLocale(<ArchivedAssignmentActions assignment={assignment("old", "ARCHIVED")} onChanged={onChanged} />);
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  const confirm = within(screen.getByRole("dialog")).getByRole("button", { name: "Restore" });
  fireEvent.click(confirm); fireEvent.click(confirm);
  expect(assignmentsApi.restoreAssignment).toHaveBeenCalledOnce();
  resolve();
  await screen.findByText(/change was saved, but the updated content could not be loaded/);
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(2));
  expect(assignmentsApi.restoreAssignment).toHaveBeenCalledOnce();
});

it("localizes a revoked assignment permission without claiming restoration succeeded", async () => {
  assignmentsApi.restoreAssignment.mockRejectedValue(new ApiError("CLASSROOM_CAPABILITY_REQUIRED", "Not permitted", 403));
  const onChanged = vi.fn();
  renderWithLocale(<ArchivedAssignmentActions assignment={assignment("old", "ARCHIVED")} onChanged={onChanged} />);
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  fireEvent.click(screen.getByRole("button", { name: "Khôi phục" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Khôi phục" }));
  expect(await within(screen.getByRole("dialog")).findByRole("alert")).toHaveTextContent("Quyền trong lớp không còn cho phép");
  expect(onChanged).not.toHaveBeenCalled();
});

it("offers archived resource and topic restoration as drafts with confirmation", async () => {
  const onRefresh = vi.fn().mockResolvedValue(undefined);
  panel({ canAuthor: true, canInspect: true, onRefresh, data: { ...data, sections: [{ ...section("reading", 0), status: "ARCHIVED" }], resources: [{ ...data.resources[0], status: "ARCHIVED" }] } });
  const topic = group("Topic reading");
  fireEvent.click(within(topic).getByText("Topic actions"));
  fireEvent.click(within(topic).getByRole("button", { name: "Restore" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.updateSection).toHaveBeenCalledExactlyOnceWith("room", "reading", { status: "DRAFT" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  fireEvent.click(toggle("Archived resources"));
  const resourceGroup = group("Archived resources");
  expect(within(resourceGroup).getByRole("button", { name: "Restore" }).closest("details")).toBeNull();
  fireEvent.click(within(resourceGroup).getByRole("button", { name: "Restore" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.updateResource).toHaveBeenCalledExactlyOnceWith("room", "notes", { status: "DRAFT" }));
  expect(onRefresh).toHaveBeenCalledTimes(2);
});

it("opens only the first populated topic and has one topic toggle with an accurate combined count", () => {
  panel();
  expect(toggle("Topic empty")).toHaveAttribute("aria-expanded", "false");
  expect(toggle("Topic reading")).toHaveAttribute("aria-expanded", "true");
  expect(toggle("Topic reading")).toHaveTextContent("2 items");
  expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "false");
  expect(within(group("Topic reading")).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.queryByText(/^Learning materials \(/)).not.toBeInTheDocument();
});
it("keeps empty topics compact, revealing an honest empty state only on demand", () => {
  panel(); expect(toggle("Topic empty")).toHaveTextContent("No content yet");
  expect(screen.queryByText("This topic has no learning content yet.")).not.toBeInTheDocument();
  fireEvent.click(toggle("Topic empty")); expect(screen.getByText("This topic has no learning content yet.")).toBeInTheDocument();
  expect(within(group("Topic empty")).queryByText("Add resource")).not.toBeInTheDocument();
});
it("keeps canonical unplaced work accessible in a secondary closed group", () => {
  panel(); expect(toggle("Not assigned to a topic")).toHaveAttribute("aria-expanded", "false");
  expect(toggle("Not assigned to a topic")).toHaveTextContent("1 item");
  fireEvent.click(toggle("Not assigned to a topic")); expect(within(group("Not assigned to a topic")).getByText("Fictional practice u")).toBeInTheDocument();
});
it("separates placed and unplaced archived assignments into one closed historical group", () => {
  panel(); expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false"); expect(toggle("Archived assignments")).toHaveTextContent("2 assignments");
  expect(within(group("Topic reading")).queryByText("Fictional practice old")).not.toBeInTheDocument();
  fireEvent.click(toggle("Archived assignments")); expect(within(group("Archived assignments")).getAllByRole("listitem")).toHaveLength(2);
  expect(within(group("Archived assignments")).queryByText("Open assignment")).not.toBeInTheDocument();
});
it("renders archived-only work without a fake uncategorized topic or active-content empty panel", () => {
  panel({ data: { revision: 0, sections: [], resources: [], items: [] }, assignments: [assignment("old", "ARCHIVED")] });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false"); expect(screen.queryByRole("region", { name: "Not assigned to a topic" })).not.toBeInTheDocument();
  expect(screen.queryByText("No course topics yet.")).not.toBeInTheDocument();
});
it("deduplicates assignments and excludes unresolved references from the visible topic count", () => {
  panel({ data: { ...data, items: [...data.items, { ...data.items[1], id: "duplicate" }, { ...data.items[0], id: "missing", resource_id: "inaccessible" }] } });
  expect(toggle("Topic reading")).toHaveTextContent("2 items"); expect(screen.getAllByText("Fictional practice a")).toHaveLength(1);
});
it("does not count draft or archived resources as student learning content", () => {
  panel({ data: { ...data, resources: [{ ...data.resources[0], status: "DRAFT" }] } });
  expect(toggle("Topic reading")).toHaveTextContent("1 item"); expect(screen.queryByText("Fictional strategy notes")).not.toBeInTheDocument();
});
it("retains user expansion choices through unrelated renders and content refreshes", () => {
  const input = props(), view = renderWithLocale(<ClassworkPanel {...input} />);
  fireEvent.click(toggle("Topic reading")); fireEvent.click(toggle("Topic writing"));
  view.rerender(<ClassworkPanel {...input} data={{ ...data, revision: 8 }} />);
  expect(toggle("Topic reading")).toHaveAttribute("aria-expanded", "false"); expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "true");
});
it("expands a topic hash and focuses its toggle without overriding a later user choice", async () => {
  window.history.replaceState(null, "", "/#section-writing"); panel();
  await waitFor(() => expect(toggle("Topic writing")).toHaveFocus()); expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(toggle("Topic writing")); expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "false");
});
it("expands and focuses assignment hash targets, including archived work", async () => {
  panel(); window.history.replaceState(null, "", "/#assignment-old"); fireEvent(window, new HashChangeEvent("hashchange"));
  await waitFor(() => expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "true"));
  expect(document.getElementById("classwork-assignment-old")).toHaveFocus();
});
it.each([
  ["NOT_STARTED", "Not started"], ["IN_PROGRESS", "In progress"], ["SUBMITTED_ON_TIME", "Submitted"], ["SUBMITTED_LATE", "Submitted late"], ["SUBMITTED_NOT_ACCEPTED", "Submission not accepted"], ["MISSED", "Missing submission"],
] as const)("shows compact %s progress without the full repeated policy panel", (submission_status, label) => {
  progress.items.a = state({ submission_status }); panel();
  const row = screen.getByText("Fictional practice a").closest("li")!;
  expect(within(row).getByText(new RegExp(label))).toBeInTheDocument();
  expect(row.querySelectorAll("dl")).toHaveLength(0); expect(within(row).queryByText(/Hard cut-off|Remaining starts|Starts used/)).not.toBeInTheDocument();
});
it("uses the student's effective deadline and shows at most three metadata parts", () => {
  progress.items.a = state({ submission_status: "IN_PROGRESS", effective_due_at: "2026-10-30T08:00:00Z", effective_cutoff_at: "2026-11-02T08:00:00Z", max_attempts: 2, attempts_used: 1 }); panel();
  const meta = screen.getByText("Fictional practice a").closest("li")!.querySelector(".classroom-assignment-meta")!;
  expect(meta.textContent).toContain("Due"); expect(meta.textContent).not.toContain("Nov"); expect(meta.textContent!.split(" · ")).toHaveLength(3);
});
it("omits empty dates and unlimited zero usage instead of showing dashes and policy noise", () => {
  progress.items.a = state(); panel(); const row = screen.getByText("Fictional practice a").closest("li")!;
  expect(row.textContent).not.toMatch(/Unlimited|0\s*\/|—|Due|cut-off/);
});
it("shows finite used attempts only when useful and never invents a score", () => {
  progress.items.a = state({ submission_status: "IN_PROGRESS", max_attempts: 2, attempts_used: 1 }); panel();
  expect(screen.getByText(/1\/2 starts/)).toBeInTheDocument(); expect(screen.queryByText(/Band\s+\d/)).not.toBeInTheDocument();
});
it("uses historical result links and details without any start action or redundant archive status", () => {
  progress.items.old = state({ availability_status: "ARCHIVED", historical: true, accepted: true, submission_status: "SUBMITTED_ON_TIME", result_attempt_id: "22222222-2222-4222-8222-222222222222" });
  const open = vi.fn(); panel({ onOpenAssignment: open }); fireEvent.click(toggle("Archived assignments"));
  const row = screen.getByText("Fictional practice old").closest("li")!;
  expect(within(row).getByRole("link", { name: "View results" })).toHaveAttribute("href", "/review/22222222-2222-4222-8222-222222222222");
  fireEvent.click(within(row).getByRole("button", { name: "View details" })); expect(open).toHaveBeenCalledWith("old");
  expect(row.textContent).not.toMatch(/Archived|Start attempt|Open assignment/);
});
it("keeps students read-only and resource bodies closed until explicitly opened", () => {
  panel(); expect(screen.queryByText("Topic actions")).not.toBeInTheDocument(); expect(screen.queryByLabelText(/Move .* to topic/)).not.toBeInTheDocument();
  expect(screen.queryByText("Read the fictional notes.")).not.toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Read resource" })); expect(screen.getByText("Read the fictional notes.")).toBeInTheDocument();
});
it("retains teacher contextual actions and a working add-resource action for an empty topic", () => {
  panel({ canAuthor: true }); fireEvent.click(toggle("Topic empty"));
  fireEvent.click(within(group("Topic empty")).getByRole("button", { name: "Create" }));
  expect(screen.getByLabelText("Resource title")).toHaveFocus();
});
it("moves canonical unplaced assignments into a topic through the existing placement API", async () => {
  panel({ canAuthor: true }); fireEvent.click(toggle("Not assigned to a topic"));
  fireEvent.change(screen.getByLabelText("Move Fictional practice u to topic"), { target: { value: "writing" } });
  await waitFor(() => expect(api.placeAssignment).toHaveBeenCalledWith("room", "writing", "u"));
});
it("preserves revision-aware keyboard reorder and move into a collapsed topic", async () => {
  panel({ canAuthor: true }); fireEvent.click(screen.getByRole("button", { name: "Move Topic writing up" }));
  await waitFor(() => expect(api.reorderSections).toHaveBeenCalledWith("room", ["empty", "writing", "reading"], 7));
  fireEvent.change(screen.getByLabelText("Move Fictional strategy notes to topic"), { target: { value: "writing" } });
  await waitFor(() => expect(api.reorderItems).toHaveBeenCalledWith("room", "writing", ["i2", "r1"], 7));
});
it("supports drops on collapsed topic headers", async () => {
  panel({ canAuthor: true });
  fireEvent.dragStart(screen.getByRole("button", { name: "Drag to move learning material: Fictional strategy notes" }), { dataTransfer: { setData: vi.fn() } });
  fireEvent.drop(group("Topic writing")); await waitFor(() => expect(api.reorderItems).toHaveBeenCalledWith("room", "writing", ["i2", "r1"], 7));
});
it("keeps expansion stable on progress refresh and displays one loading/error recovery message", async () => {
  Object.assign(progress, { loading: true }); const input = props(), view = renderWithLocale(<ClassworkPanel {...input} />);
  expect(screen.getAllByText("Loading progress…")).toHaveLength(1); fireEvent.click(toggle("Topic writing"));
  Object.assign(progress, { loading: false, error: true }); view.rerender(<ClassworkPanel {...input} />);
  expect(screen.getAllByRole("alert")).toHaveLength(1); fireEvent.click(screen.getByRole("button", { name: "Retry" })); expect(progress.refresh).toHaveBeenCalledOnce();
  expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "true");
});
it("retains revision conflict recovery and does not lose the opened topic", async () => {
  const refresh = vi.fn().mockResolvedValue(undefined); api.reorderSections.mockRejectedValueOnce(new ApiError("CLASSWORK_CHANGED", "Conflict", 409)); panel({ canAuthor: true, onRefresh: refresh });
  fireEvent.click(toggle("Topic writing")); fireEvent.click(screen.getByRole("button", { name: "Move Topic writing up" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Classwork changed elsewhere"); expect(refresh).toHaveBeenCalledOnce(); expect(toggle("Topic writing")).toHaveAttribute("aria-expanded", "true");
});
it("localizes counts, history and compact progress consistently in Vietnamese and English", () => {
  progress.items.a = state({ submission_status: "IN_PROGRESS" }); panel(); fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(toggle("Topic reading")).toHaveTextContent("2 mục"); expect(screen.getByRole("heading", { name: "Nội dung học" })).toBeInTheDocument(); expect(screen.getByText(/Đang làm/)).toBeInTheDocument();
  expect(toggle("Bài tập đã lưu trữ")).toHaveTextContent("2 bài"); expect(screen.queryByText(/Học liệu \(/)).not.toBeInTheDocument();
});
it("shows one honest empty state for a classroom with no topics or activities", () => {
  panel({ data: { revision: 0, sections: [], resources: [], items: [] }, assignments: [] }); expect(screen.getByText("No course topics yet.")).toBeInTheDocument(); expect(screen.queryByRole("list")).not.toBeInTheDocument();
});

it("searches Vietnamese topics without case or diacritics and preserves their children", () => {
  panel({ data: { ...data, sections: data.sections.map(row => row.id === "reading" ? { ...row, title: "Đọc hiểu nâng cao" } : row) } });
  fireEvent.change(screen.getByRole("searchbox", { name: "Search classroom content" }), { target: { value: "DOC HIEU" } });
  expect(within(group("Đọc hiểu nâng cao")).getAllByRole("listitem")).toHaveLength(2);
  expect(screen.queryByRole("region", { name: "Topic writing" })).not.toBeInTheDocument();
});

it("finds resources and archived assignments, then restores prior disclosure when search clears", () => {
  panel();
  const search = screen.getByRole("searchbox", { name: "Search classroom content" });
  fireEvent.change(search, { target: { value: "strategy" } });
  expect(within(group("Topic reading")).getAllByRole("listitem")).toHaveLength(1);
  fireEvent.change(search, { target: { value: "practice older" } });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Fictional practice older")).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "" } });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false");
  expect(toggle("Topic reading")).toHaveAttribute("aria-expanded", "true");
});

it("keeps observer archive details without mounting teacher controls or decorative disabled actions", () => {
  const open = vi.fn(); panel({ canAuthor: false, canAssign: false, canInspect: true, onOpenAssignment: open });
  fireEvent.click(toggle("Topic empty"));
  expect(within(group("Topic empty")).getByText("This topic has no learning content yet.")).toBeInTheDocument();
  expect(within(group("Topic empty")).queryByRole("button", { name: /Create|Add/ })).not.toBeInTheDocument();
  fireEvent.click(toggle("Archived assignments"));
  const archive = group("Archived assignments");
  fireEvent.click(within(archive).getAllByRole("button", { name: "View details" })[0]);
  expect(open).toHaveBeenCalledWith("old");
  expect(within(archive).queryByRole("button", { name: /Restore|Delete|Remove/ })).not.toBeInTheDocument();
  expect(within(archive).queryByText("Item actions")).not.toBeInTheDocument();
  expect(archive).toHaveTextContent("Assignment · Archived");
});

it("shows teacher restore, delete and details directly once on desktop", async () => {
  const onAssignmentsChanged = vi.fn().mockResolvedValue(undefined);
  panel({ canAuthor: true, canAssign: true, onAssignmentsChanged }); fireEvent.click(toggle("Archived assignments"));
  const row = screen.getByText("Fictional practice old").closest("li")!;
  const restore = within(row).getByRole("button", { name: "Restore" });
  expect(restore.closest("details")).toBeNull();
  expect(within(row).getByRole("button", { name: "Delete permanently" }).closest("details")).toBeNull();
  expect(within(row).getAllByRole("button", { name: "View details" })).toHaveLength(1);
  fireEvent.click(restore); fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(onAssignmentsChanged).toHaveBeenCalledOnce());
});

it("renders a single contextual set of archive actions on compact viewports", () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  try {
    panel({ canAuthor: true, canAssign: true }); fireEvent.click(toggle("Archived assignments"));
    const row = screen.getByText("Fictional practice old").closest("li")!;
    const menu = row.querySelector("details")!;
    expect(menu).not.toBeNull(); fireEvent.click(within(row).getByText("Item actions"));
    expect(menu.querySelectorAll("button")).toHaveLength(4);
    expect(within(row).getAllByRole("button", { name: "Restore" })).toHaveLength(1);
    expect(within(row).getAllByRole("button", { name: "View details" })).toHaveLength(1);
    expect(within(row).getByRole("button", { name: "View details" }).closest("details")).toBe(menu);
  } finally { vi.unstubAllGlobals(); }
});

it("searches within archives while preserving the total count and other classroom topics", () => {
  panel({ assignments: [...assignments, { ...assignment("vietnamese", "ARCHIVED"), title: "Đề ôn tập nâng cao" }] });
  const search = within(group("Archived assignments")).getByRole("searchbox", { name: "Search archived assignments" });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false");
  fireEvent.change(search, { target: { value: "DE ON TAP" } });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "true");
  expect(toggle("Archived assignments")).toHaveTextContent("3 assignments");
  expect(within(group("Archived assignments")).getAllByRole("listitem")).toHaveLength(1);
  expect(screen.getByText("Đề ôn tập nâng cao")).toBeInTheDocument();
  expect(screen.getByText("Fictional strategy notes")).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "no such work" } });
  expect(within(group("Archived assignments")).getByRole("status")).toHaveTextContent("No matching topics, resources or assignments.");
  fireEvent.change(search, { target: { value: "" } });
  expect(within(group("Archived assignments")).getAllByRole("listitem")).toHaveLength(3);
});

it("keeps archive disclosure usable during a global search without changing the previous choice", () => {
  panel();
  const search = screen.getByRole("searchbox", { name: "Search classroom content" });
  fireEvent.change(search, { target: { value: "practice older" } });
  fireEvent.click(toggle("Archived assignments"));
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle("Archived assignments"));
  expect(screen.getByText("Fictional practice older")).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "" } });
  expect(toggle("Archived assignments")).toHaveAttribute("aria-expanded", "false");
});
