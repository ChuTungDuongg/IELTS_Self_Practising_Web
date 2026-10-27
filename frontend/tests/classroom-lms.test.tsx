import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderWithLocale } from "./locale-test-utils";
import { ClassroomWorkspace } from "@/features/classrooms/content/classroom-workspace";
import { ClassroomHeader } from "@/features/classrooms/lms/classroom-header";
import { GradebookPanel } from "@/features/classrooms/lms/gradebook";
import { StaffManagement } from "@/features/classrooms/lms/staff-management";
import { PostCard } from "@/features/classrooms/content/post-card";
import { AssignmentProgressProvider } from "@/features/classrooms/scheduling/progress-provider";

const api = vi.hoisted(() => ({ getClasswork: vi.fn(), listFeed: vi.fn(), getGradebook: vi.fn(), updateGradePolicy: vi.fn(), getStaff: vi.fn(), inviteStaff: vi.fn() }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), getClasswork: api.getClasswork, listFeed: api.listFeed }));
vi.mock("@/lib/api/classroom-lms", async original => ({ ...await original<object>(), ...api }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const room = { id: "room", teacher_id: "owner", name: "BandPilot Evening IELTS", teacher_name: "Tutor", active_member_count: 3, description: "Our classroom", status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
const assignment = { id: "assignment", classroom_id: "room", test_version_id: "version", created_by_user_id: "owner", title: "Reading weekly practice", note: null, status: "ACTIVE" as const, created_at: "now", archived_at: null, due_at: "2026-10-30T16:59:00Z", cutoff_at: "2026-10-31T16:59:00Z" };
const score = { assignment_id: "assignment", root_id: "root", kind: "ATTEMPT" as const, result_attempt_id: "root", skill: "WRITING", scope: "FULL_MODULE", context: "WRITING:FULL_MODULE", band: null, raw_score: null, max_score: null, provenance: "PENDING_HUMAN" as const, finished_at: "2026-10-27T08:00:00Z", accepted: true, late: false, submission_status: "SUBMITTED_ON_TIME", mixed_context_fallback: false, breakdown: [] };
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); api.getClasswork.mockResolvedValue({ revision: 0, sections: [], resources: [], items: [] }); api.listFeed.mockResolvedValue({ items: [], next_cursor: null }); api.getStaff.mockResolvedValue([]); api.inviteStaff.mockResolvedValue({}); api.updateGradePolicy.mockResolvedValue({}); api.getGradebook.mockResolvedValue({ assignments: [{ id: "assignment", title: assignment.title, grade_selection: "LATEST_ACCEPTED", policy_revision: 1 }], students: [{ student_id: "learner", display_name: "Mina", active_member: true, cells: [{ assignment_id: "assignment", submission_status: "SUBMITTED_ON_TIME", attempts_used: 1, eligible: true, score }] }], total_students: 1, total_assignments: 1 }); });

it("provides a compact course header and keeps archive inside its management disclosure", () => {
  const create = vi.fn(), manage = vi.fn();
  renderWithLocale(<ClassroomHeader classroom={room} canCreate onCreate={create} onManage={manage} management={<button>Archive</button>} />);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(room.name);
  expect(screen.getByRole("button", { name: "Archive" }).closest("details")).not.toHaveAttribute("open");
  fireEvent.click(screen.getByText("Create")); fireEvent.click(screen.getByRole("button", { name: "Create assignment" })); expect(create).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByText("Manage class"));
  expect(screen.getByRole("button", { name: "Archive" }).closest("details")).toHaveAttribute("open");
});

it("offers staff Gradebook navigation while keeping the assignment creation form closed", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={room} user={{ id: "owner", role: "TEACHER" }} assignments={[]} assignmentForm={<p>Assignment creation fields</p>} people={<p>People controls</p>} />);
  await screen.findByText("No classroom updates yet.");
  expect(screen.getByRole("tab", { name: "Gradebook" })).toBeInTheDocument();
  expect(screen.queryByText("Assignment creation fields")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Create")); fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  expect(screen.getByRole("tab", { name: "Assignments" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Assignment creation fields")).toBeInTheDocument();
  expect(document.querySelector(".classroom-course-nav")).toBeNull();
});

it("hides staff navigation and creation controls from students and explains empty Classwork", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={room} user={{ id: "learner", role: "USER" }} assignments={[]} />);
  expect(screen.queryByRole("tab", { name: "Gradebook" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "People" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Classwork" }));
  expect(await screen.findByText("No course topics yet.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create first topic" })).not.toBeInTheDocument();
});

it("keeps Admin in the shared observer workspace without teacher or student actions", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={{ ...room, capabilities: ["roster.view", "grades.view", "analytics.view", "content.manage", "assignments.manage", "grades.edit"] }} user={{ id: "admin", role: "ADMIN" }} assignments={[assignment]} management={<button>Forbidden management</button>} assignmentForm={<p>Forbidden assignment fields</p>} people={<p>Read-only roster</p>} />);
  expect(screen.getByText("Observer mode · Read only")).toBeInTheDocument();
  expect(screen.queryByText("Manage class")).not.toBeInTheDocument();
  expect(screen.queryByText("Create")).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "My Progress" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "People" }));
  expect(screen.getByText("Read-only roster")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Assignments" }));
  expect(screen.queryByText("Forbidden assignment fields")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Start assignment" })).not.toBeInTheDocument();
  expect(screen.queryByText("No deadline")).not.toBeInTheDocument();
});

it("filters feed content through the paginated backend query", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={room} user={{ id: "owner", role: "TEACHER" }} assignments={[]} />);
  await screen.findByText("No classroom updates yet.");
  fireEvent.click(within(screen.getByRole("group", { name: "Feed type" })).getByRole("button", { name: "Assignments" }));
  await waitFor(() => expect(api.listFeed).toHaveBeenLastCalledWith("room", expect.objectContaining({ contentKind: "ASSIGNMENT_ACTIVITY" })));
});

it("uses a real assignment title and grouped localized deadlines in assignment feed cards", async () => {
  renderWithLocale(<AssignmentProgressProvider classroomId="room" ids={[assignment.id]} assignments={[assignment]} staff><PostCard classroomId="room" post={{ id: "post", assignment_id: assignment.id, kind: "ASSIGNMENT_ACTIVITY", title: null, body: "", status: "PUBLISHED", pinned: false, locked: true, author_id: "owner", author_name: "Tutor", author_role: "TEACHER", created_at: "2026-10-27T08:00:00Z", updated_at: "2026-10-27T08:00:00Z", published_at: "2026-10-27T08:00:00Z", comment_count: 0, resource_ids: [] }} resources={[]} userId="owner" canAuthor archived={false} admin={false} onRefresh={vi.fn()} onOpenAssignment={vi.fn()} /></AssignmentProgressProvider>);
  expect(screen.getByRole("heading", { name: assignment.title })).toBeInTheDocument();
  expect(screen.getByText("Due")).toBeInTheDocument();
  expect(screen.getByText("Cut-off")).toBeInTheDocument();
  expect(document.querySelector(`time[datetime="${assignment.due_at}"]`)).toBeInTheDocument();
  expect(document.querySelector(`time[datetime="${assignment.cutoff_at}"]`)).toBeInTheDocument();
  expect(screen.queryByText(assignment.due_at)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open assignment" })).toBeInTheDocument();
});

it("renders pending human grades without inventing a zero and submits Gradebook filters", async () => {
  renderWithLocale(<GradebookPanel classroomId="room" assignments={[assignment]} canEdit />);
  expect(await screen.findByRole("button", { name: "Mina" })).toBeInTheDocument();
  expect(screen.getByText("Awaiting human grading")).toBeInTheDocument();
  expect(screen.getByText("—")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search students"), { target: { value: "Mina" } });
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  await waitFor(() => expect(api.getGradebook).toHaveBeenLastCalledWith("room", expect.objectContaining({ search: "Mina", offset: 0 }), expect.any(AbortSignal)));
});

it("requires explicit staff invitation input and hides staff mutations from a TA", async () => {
  const view = renderWithLocale(<StaffManagement classroomId="room" canManage archived={false} />);
  fireEvent.click(screen.getAllByText("Invite staff").find(element => element.tagName === "SUMMARY")!);
  fireEvent.change(screen.getByLabelText("Account email"), { target: { value: "staff@example.com" } });
  fireEvent.change(screen.getByLabelText("Classroom role"), { target: { value: "TEACHING_ASSISTANT" } });
  fireEvent.click(screen.getByLabelText("View analytics"));
  fireEvent.click(screen.getByRole("button", { name: "Invite staff" }));
  await waitFor(() => expect(api.inviteStaff).toHaveBeenCalledWith("room", expect.objectContaining({ email: "staff@example.com", staff_role: "TEACHING_ASSISTANT", analytics_view: true })));
  view.unmount(); renderWithLocale(<StaffManagement classroomId="room" canManage={false} archived={false} />);
  expect(screen.queryByText("Invite staff")).not.toBeInTheDocument();
});

it("keeps archived classrooms readable without creation actions", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={{ ...room, status: "ARCHIVED" }} user={{ id: "owner", role: "TEACHER" }} assignments={[]} assignmentForm={<p>Hidden form</p>} />);
  expect(screen.getByText("This classroom is archived. Retained content is available to read.")).toHaveAttribute("role", "status");
  expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Gradebook" })).toBeInTheDocument();
});

it("contains matrix overflow and provides tablet/mobile and focus rules", () => {
  const css = readFileSync(resolve("src/features/classrooms/lms/lms.css"), "utf8");
  expect(css).toContain("overflow:auto"); expect(css).toContain("position:sticky");
  expect(css).toContain("max-width:768px"); expect(css).toContain("max-width:480px"); expect(css).toContain(":focus-visible");
});
