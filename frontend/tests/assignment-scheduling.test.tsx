import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { serializeSchedule, localDateTime, type AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { ProgressSummary } from "@/features/classrooms/scheduling/progress-summary";
import { ExtensionEditor } from "@/features/classrooms/scheduling/extension-editor";
import { AssignmentMonitoringPanel } from "@/features/classrooms/scheduling/assignment-monitoring";
import { AssignmentCalendarPanel } from "@/features/classrooms/scheduling/assignment-calendar";
import { ScheduleEditor } from "@/features/classrooms/scheduling/schedule-editor";
import { AssignmentProgressProvider } from "@/features/classrooms/scheduling/progress-provider";
import { AssignmentList } from "@/features/classrooms/assignment-list";

const api = vi.hoisted(() => ({ getMonitoring: vi.fn(), getAssignmentCalendar: vi.fn(), updateAssignmentSchedule: vi.fn(), saveExtension: vi.fn(), revokeExtension: vi.fn(), getAssignmentProgress: vi.fn(), startAssignment: vi.fn(), push: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api/assignment-scheduling", async original => ({ ...await original<object>(), ...api }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), startAssignment: api.startAssignment }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push, refresh: api.refresh }) }));
const assignment = { id: "d19ab9d2-1e11-4c54-aac9-231f60b0eb7c", classroom_id: "b2a89fa8-5393-4416-b960-19caa18846a6", test_version_id: "e4b688d8-19a0-4627-94f1-72f540ee2c97", created_by_user_id: "a081075c-4b55-4b15-a380-89e5c616ebd9", title: "Reading workshop", note: null, status: "ACTIVE" as const, created_at: "2026-10-27T12:00:00Z", archived_at: null, policy_revision: 2, available_from: null, due_at: "2026-11-07T12:00:00Z", cutoff_at: "2026-11-09T12:00:00Z", max_attempts: 2, allow_late_submission: true };
const progress: AssignmentProgress = { assignment_id: assignment.id, availability_status: "OPEN", submission_status: "IN_PROGRESS", available_from: null, effective_due_at: assignment.due_at, effective_cutoff_at: assignment.cutoff_at, max_attempts: 2, attempts_used: 1, attempts_remaining: 1, can_start: true, start_blocked_reason: null, can_resume: true, latest_attempt_id: "attempt", latest_session_id: null, resume_attempt_id: "attempt", resume_session_id: null, result_attempt_id: null, completed_at: null, late: false, accepted: false, historical: false };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); api.getAssignmentProgress.mockResolvedValue({ items: [progress], total: 1 }); api.getMonitoring.mockResolvedValue({ items: [], total: 0, summary: { eligible_students: 0 } }); api.getAssignmentCalendar.mockResolvedValue({ items: [], total: 0 }); api.updateAssignmentSchedule.mockResolvedValue(assignment); api.saveExtension.mockResolvedValue({}); });

it("serializes local inputs to aware UTC instants and rejects invalid order/limits", () => {
  const form = new FormData(); form.set("available_from", "2026-11-02T10:00"); form.set("due_at", "2026-11-07T23:59"); form.set("cutoff_at", "2026-11-09T23:59"); form.set("max_attempts", "2"); form.set("allow_late_submission", "on");
  const policy = serializeSchedule(form); expect(policy.due_at).toBe(new Date("2026-11-07T23:59").toISOString()); expect(policy.due_at).toMatch(/Z$/); expect(localDateTime(policy.due_at)).toBe("2026-11-07T23:59");
  form.set("max_attempts", "0"); expect(() => serializeSchedule(form)).toThrow(); form.set("max_attempts", "2"); form.set("cutoff_at", "2026-11-01T00:00"); expect(() => serializeSchedule(form)).toThrow();
});
it("shows authoritative progress and resumes without creating another start", () => {
  renderWithLocale(<ProgressSummary assignmentId={assignment.id} value={progress} actions />);
  expect(screen.getByText(/Starts used: 1 \/ 2/)).toBeInTheDocument(); expect(screen.getByRole("link", { name: "Continue attempt" })).toHaveAttribute("href", "/attempt/attempt"); expect(api.startAssignment).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Switch to Vietnamese")); expect(screen.getByText("Đang làm")).toBeInTheDocument();
});
it("disables starts after limit but keeps Continue available", async () => {
  api.getAssignmentProgress.mockResolvedValue({ items: [{ ...progress, can_start: false, attempts_remaining: 0, start_blocked_reason: "ASSIGNMENT_ATTEMPT_LIMIT" }], total: 1 });
  renderWithLocale(<AssignmentProgressProvider classroomId={assignment.classroom_id} ids={[assignment.id]}><AssignmentList assignments={[assignment]} /></AssignmentProgressProvider>);
  await screen.findByText(/All starts have been used/); expect(screen.getByRole("button", { name: "Start assignment" })).toBeDisabled(); expect(screen.getByRole("link", { name: "Continue attempt" })).toBeInTheDocument();
});
it("requires confirmation before saving schedule changes", async () => {
  renderWithLocale(<ScheduleEditor assignment={assignment} onSaved={vi.fn()} onCancel={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Maximum starts"), { target: { value: "3" } }); fireEvent.click(screen.getByRole("button", { name: "Save schedule" })); expect(api.updateAssignmentSchedule).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save schedule" }));
  await waitFor(() => expect(api.updateAssignmentSchedule).toHaveBeenCalledWith(assignment.classroom_id, assignment.id, expect.objectContaining({ expected_revision: 2, max_attempts: 3 })));
});
it("saves only the selected student's explicit extension", async () => {
  renderWithLocale(<ExtensionEditor classroomId="room" assignmentId="assignment" studentId="student" name="Learner" value={null} onDone={vi.fn()} />);
  fireEvent.click(screen.getByLabelText("Override due date")); fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-08T23:59" } }); fireEvent.change(screen.getByLabelText("Additional starts"), { target: { value: "1" } }); fireEvent.click(screen.getByRole("button", { name: "Save extension" }));
  expect(api.saveExtension).not.toHaveBeenCalled(); fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save extension" }));
  await waitFor(() => expect(api.saveExtension).toHaveBeenCalledWith("room", "assignment", "student", expect.objectContaining({ override_due: true, additional_attempts: 1 })));
});
it("filters monitoring with server-scoped queries and handles empty results", async () => {
  renderWithLocale(<AssignmentMonitoringPanel classroomId="room" assignmentId="assignment" canEdit={false} />);
  await screen.findByText("No students match this view."); fireEvent.change(screen.getByLabelText("Submission"), { target: { value: "MISSED" } });
  await waitFor(() => expect(api.getMonitoring).toHaveBeenLastCalledWith("room", "assignment", expect.objectContaining({ status: "MISSED", offset: 0 }), expect.any(AbortSignal)));
  expect(screen.queryByRole("button", { name: "Individual extension" })).not.toBeInTheDocument();
});
it("renders assignment-derived calendar due and cutoff separately", async () => {
  api.getAssignmentCalendar.mockResolvedValue({ items: [{ assignment_id: assignment.id, title: "Reading workshop", kind: "DUE", at: assignment.due_at, progress: null }, { assignment_id: assignment.id, title: "Reading workshop", kind: "CUTOFF", at: assignment.cutoff_at, progress: null }], total: 2 });
  const open = vi.fn(); renderWithLocale(<AssignmentCalendarPanel classroomId="room" onOpenAssignment={open} />);
  await screen.findByText("Cut-off"); expect(screen.getByText("Due")).toBeInTheDocument(); fireEvent.click(screen.getAllByRole("button", { name: "Reading workshop" })[0]); expect(open).toHaveBeenCalledWith(assignment.id);
});
it("retains existing submission links while classroom is archived", () => {
  renderWithLocale(<ProgressSummary assignmentId={assignment.id} value={{ ...progress, availability_status: "ARCHIVED", submission_status: "SUBMITTED_LATE", completed_at: assignment.due_at, accepted: true, result_attempt_id: "result", can_resume: false }} actions />);
  expect(screen.getByRole("link", { name: "View submission" })).toHaveAttribute("href", "/review/result"); expect(screen.getByText("Submitted late")).toBeInTheDocument();
});
