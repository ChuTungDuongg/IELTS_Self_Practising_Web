import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ClassroomDirectory } from "@/features/classrooms/classroom-directory";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ create: vi.fn(), push: vi.fn(), refresh: vi.fn(), calendar: vi.fn(), feed: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push, refresh: api.refresh }) }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), createClassroom: api.create }));
vi.mock("@/lib/api/assignment-scheduling", async original => ({ ...await original<object>(), getAssignmentCalendar: api.calendar }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), listFeed: api.feed }));
vi.mock("@/features/classrooms/lms/staff-management", () => ({ StaffInvitationInbox: () => null }));
const base = { teacher_id: "owner", teacher_name: "Teacher One", description: "Practice", active_member_count: 2, archived_at: null, updated_at: "2026-01-01T00:00:00Z" };
const rooms = [
  { ...base, id: "first", name: "Alpha", status: "ACTIVE" as const, classroom_role: "OWNER" as const, membership_active: null, created_at: "2026-01-01T00:00:00Z" },
  { ...base, id: "second", name: "Beta", teacher_id: "other", teacher_name: "Teacher Two", status: "ARCHIVED" as const, classroom_role: "STUDENT" as const, membership_active: false, created_at: "2026-02-01T00:00:00Z" },
  { ...base, id: "third", name: "Gamma", teacher_id: "other", status: "ACTIVE" as const, classroom_role: "STUDENT" as const, membership_active: true, created_at: "2026-03-01T00:00:00Z" },
];
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); api.calendar.mockResolvedValue({ items: [], total: 0 }); api.feed.mockResolvedValue({ items: [], next_cursor: null }); Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.setAttribute("open", ""); } }); Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); } }); });

it("filters, sorts and navigates real classrooms while excluding historical attendance", () => {
  renderWithLocale(<ClassroomDirectory items={rooms} invitations={[]} user={{ id: "owner", role: "TEACHER" }} />);
  expect(screen.getByText("Total classrooms").previousElementSibling).toHaveTextContent("3");
  expect(screen.getByText("Classrooms you attend").previousElementSibling).toHaveTextContent("1");
  expect(screen.getAllByRole("link", { name: /View overview/ })[0]).toHaveAttribute("href", "/classrooms/third/overview");
  fireEvent.click(screen.getByRole("button", { name: "Archived (1)" }));
  expect(screen.getByRole("heading", { name: "Beta" })).toBeInTheDocument(); expect(screen.queryByRole("heading", { name: "Alpha" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search by classroom, description or teacher..."), { target: { value: "Teacher Two" } });
  expect(screen.getByRole("heading", { name: "Beta" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "All (3)" }));
  fireEvent.change(screen.getByLabelText("Search by classroom, description or teacher..."), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "oldest" } });
  expect(screen.getAllByRole("article")[0]).toHaveTextContent("Alpha");
});

it("opens a creation dialog for teachers and sends a created classroom to its overview", async () => {
  api.create.mockResolvedValue(rooms[0]);
  renderWithLocale(<ClassroomDirectory items={[]} invitations={[]} user={{ id: "owner", role: "TEACHER" }} />);
  fireEvent.click(screen.getByRole("button", { name: "Create classroom" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Classroom name"), { target: { value: "Alpha" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Create classroom" }));
  await waitFor(() => expect(api.push).toHaveBeenCalledWith("/teacher/classrooms/first/overview"));
});

it("does not offer creation or teacher metrics to students", () => {
  renderWithLocale(<ClassroomDirectory items={[]} invitations={[]} user={{ id: "student", role: "STUDENT" }} />);
  expect(screen.queryByRole("button", { name: "Create classroom" })).not.toBeInTheDocument();
  expect(screen.queryByText("Classrooms you teach")).not.toBeInTheDocument();
  expect(screen.getByText("No classrooms found.")).toBeInTheDocument();
});

it("loads only the selected classroom and month, aborts stale requests, and links actual day events", async () => {
  const today = new Date(), first = new Date(today.getFullYear(), today.getMonth(), 1, 12), second = new Date(today.getFullYear(), today.getMonth(), 2, 12);
  let finishOld!: (value: unknown) => void;
  api.calendar.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; })).mockResolvedValueOnce({ items: [
    { assignment_id: "due-id", title: "Reading deadline", kind: "DUE", at: first.toISOString(), progress: null },
    { assignment_id: "other-id", title: "Other day", kind: "DUE", at: second.toISOString(), progress: null },
  ], total: 51 });
  api.feed.mockResolvedValue({ items: [{ id: "post-id", kind: "ANNOUNCEMENT", title: "Class update", author_name: "Teacher", created_at: first.toISOString(), published_at: first.toISOString() }, { id: "activity-id", assignment_id: "assignment-id", kind: "ASSIGNMENT_ACTIVITY", title: "Assignment activity", author_name: "Teacher", created_at: first.toISOString() }, { id: "resource-id", kind: "RESOURCE_ACTIVITY", title: "Resource activity", author_name: "Teacher", created_at: first.toISOString() }], next_cursor: null });
  renderWithLocale(<ClassroomDirectory items={rooms} invitations={[]} user={{ id: "owner", role: "TEACHER" }} />);
  await waitFor(() => expect(api.calendar).toHaveBeenCalledTimes(1));
  const firstSignal = api.calendar.mock.calls[0][4] as AbortSignal;
  const firstFeedSignal = api.feed.mock.calls[0][1].signal as AbortSignal;
  fireEvent.change(screen.getByLabelText("Choose classroom"), { target: { value: "second" } });
  await waitFor(() => expect(api.calendar).toHaveBeenCalledTimes(2));
  expect(firstSignal.aborted).toBe(true);
  expect(firstFeedSignal.aborted).toBe(true);
  finishOld({ items: [{ assignment_id: "stale", title: "Stale event", kind: "DUE", at: first.toISOString(), progress: null }], total: 1 });
  fireEvent.click(screen.getByRole("button", { name: new RegExp(new Intl.DateTimeFormat("en", { dateStyle: "full" }).format(first)) }));
  expect(await screen.findByRole("link", { name: "Reading deadline" })).toHaveAttribute("href", "/classrooms/second?assignment=due-id");
  expect(screen.queryByText("Stale event")).not.toBeInTheDocument(); expect(screen.queryByRole("link", { name: "Other day" })).not.toBeInTheDocument();
  expect(screen.getByText(/Only the first 50 events/)).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Class update" })).toHaveAttribute("href", "/classrooms/second?post=post-id");
  expect(screen.getByRole("link", { name: "Assignment activity" })).toHaveAttribute("href", "/classrooms/second?assignment=assignment-id");
  expect(screen.getByRole("link", { name: "Resource activity" })).toHaveAttribute("href", "/classrooms/second#classwork-resource-resource-id");
  const secondSignal = api.calendar.mock.calls[1][4] as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "Next month" }));
  await waitFor(() => expect(api.calendar).toHaveBeenCalledTimes(3));
  expect(secondSignal.aborted).toBe(true);
});
