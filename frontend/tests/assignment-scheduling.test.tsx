import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { serializeSchedule, localDateTime, type AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { ProgressSummary } from "@/features/classrooms/scheduling/progress-summary";
import { ExtensionEditor } from "@/features/classrooms/scheduling/extension-editor";
import { AssignmentMonitoringPanel } from "@/features/classrooms/scheduling/assignment-monitoring";
import { AssignmentCalendarPanel } from "@/features/classrooms/scheduling/assignment-calendar";
import { ScheduleEditor } from "@/features/classrooms/scheduling/schedule-editor";
import { AssignmentProgressProvider, useAssignmentProgress } from "@/features/classrooms/scheduling/progress-provider";
import { AssignmentList } from "@/features/classrooms/assignment-list";
import { loadCalendarEvents, type CalendarEvent } from "@/features/classrooms/scheduling/calendar-data";

const api = vi.hoisted(() => ({ getMonitoring: vi.fn(), getAssignmentCalendar: vi.fn(), updateAssignmentSchedule: vi.fn(), saveExtension: vi.fn(), revokeExtension: vi.fn(), getAssignmentProgress: vi.fn(), startAssignment: vi.fn(), push: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api/assignment-scheduling", async original => ({ ...await original<object>(), ...api }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), startAssignment: api.startAssignment }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push, refresh: api.refresh }) }));
const assignment = { id: "d19ab9d2-1e11-4c54-aac9-231f60b0eb7c", classroom_id: "b2a89fa8-5393-4416-b960-19caa18846a6", test_version_id: "e4b688d8-19a0-4627-94f1-72f540ee2c97", created_by_user_id: "a081075c-4b55-4b15-a380-89e5c616ebd9", title: "Reading workshop", note: null, status: "ACTIVE" as const, created_at: "2026-10-27T12:00:00Z", archived_at: null, policy_revision: 2, available_from: null, due_at: "2026-11-07T12:00:00Z", cutoff_at: "2026-11-09T12:00:00Z", max_attempts: 2, allow_late_submission: true };
const progress: AssignmentProgress = { assignment_id: assignment.id, availability_status: "OPEN", submission_status: "IN_PROGRESS", available_from: null, effective_due_at: assignment.due_at, effective_cutoff_at: assignment.cutoff_at, max_attempts: 2, attempts_used: 1, attempts_remaining: 1, can_start: true, start_blocked_reason: null, can_resume: true, latest_attempt_id: "attempt", latest_session_id: null, resume_attempt_id: "attempt", resume_session_id: null, result_attempt_id: null, completed_at: null, late: false, accepted: false, historical: false };
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); api.getAssignmentProgress.mockResolvedValue({ items: [progress], total: 1 }); api.getMonitoring.mockResolvedValue({ items: [], total: 0, summary: { eligible_students: 0 } }); api.getAssignmentCalendar.mockResolvedValue({ items: [], total: 0 }); api.updateAssignmentSchedule.mockResolvedValue(assignment); api.saveExtension.mockResolvedValue({}); });
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(new Date(2026, 9, 15, 12)); });
afterEach(() => vi.useRealTimers());

it("serializes local inputs to aware UTC instants and rejects invalid order/limits", () => {
  const form = new FormData(); form.set("available_from", "2026-11-02T10:00"); form.set("due_at", "2026-11-07T23:59"); form.set("cutoff_at", "2026-11-09T23:59"); form.set("max_attempts", "2"); form.set("allow_late_submission", "on");
  const policy = serializeSchedule(form); expect(policy.due_at).toBe(new Date("2026-11-07T23:59").toISOString()); expect(policy.due_at).toMatch(/Z$/); expect(localDateTime(policy.due_at)).toBe("2026-11-07T23:59");
  form.set("max_attempts", "0"); expect(() => serializeSchedule(form)).toThrow(); form.set("max_attempts", "2"); form.set("cutoff_at", "2026-11-01T00:00"); expect(() => serializeSchedule(form)).toThrow();
});
it("reuses progress for the same assignment set across reordered tab inputs", async () => {
  const renders = vi.fn();
  function Probe() {
    const state = useAssignmentProgress(); renders();
    return <p>{state?.loading ? "Loading progress" : "Progress ready"}</p>;
  }
  const child = <Probe />;
  const view = renderWithLocale(<AssignmentProgressProvider classroomId="room" ids={["a", "b"]}>{child}</AssignmentProgressProvider>);
  await screen.findByText("Progress ready");
  const before = renders.mock.calls.length;
  view.rerender(<AssignmentProgressProvider classroomId="room" ids={["b", "a", "a"]}>{child}</AssignmentProgressProvider>);
  await screen.findByText("Progress ready");
  expect(api.getAssignmentProgress).toHaveBeenCalledTimes(1);
  expect(renders).toHaveBeenCalledTimes(before);
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
  fireEvent.click(screen.getByRole("button", { name: "Next month" }));
  const chip = await screen.findByRole("button", { name: /^Reading workshop · Due ·/ });
  expect(screen.getByRole("button", { name: /^Reading workshop · Cut-off ·/ })).toBeInTheDocument();
  fireEvent.click(chip);
  fireEvent.click(within(screen.getByRole("complementary", { name: "Selected day details" })).getByRole("button", { name: "Assignment details" }));
  expect(open).toHaveBeenCalledWith(assignment.id);
});
it("retains existing submission links while classroom is archived", () => {
  renderWithLocale(<ProgressSummary assignmentId={assignment.id} value={{ ...progress, availability_status: "ARCHIVED", submission_status: "SUBMITTED_LATE", completed_at: assignment.due_at, accepted: true, result_attempt_id: "result", can_resume: false }} actions />);
  expect(screen.getByRole("link", { name: "View submission" })).toHaveAttribute("href", "/review/result"); expect(screen.getByText("Submitted late")).toBeInTheDocument();
});

function calendarEvent(index = 0, kind: CalendarEvent["kind"] = "DUE"): CalendarEvent {
  return { assignment_id: `assignment-${index}`, title: `Fictional lesson ${index}`, kind, at: new Date(2026, 9, 15, 12).toISOString(), progress: null };
}
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }

it("loads all calendar pages before publishing the visible range", async () => {
  const events = Array.from({ length: 123 }, (_, index) => calendarEvent(index));
  api.getAssignmentCalendar.mockImplementation(async (_room, _start, _end, offset) => ({ items: events.slice(offset, offset + 50), total: 123 }));
  const controller = new AbortController();
  expect(await loadCalendarEvents("room", "start", "end", controller.signal)).toHaveLength(123);
  expect(api.getAssignmentCalendar.mock.calls.map(call => call[3])).toEqual([0, 50, 100]);
  expect(api.getAssignmentCalendar.mock.calls.every(call => call[4] === controller.signal)).toBe(true);
});
it("cancels calendar pagination before requesting another page", async () => {
  const first = deferred<{ items: CalendarEvent[]; total: number }>();
  api.getAssignmentCalendar.mockReturnValue(first.promise);
  const controller = new AbortController(), result = loadCalendarEvents("room", "start", "end", controller.signal);
  const rejected = expect(result).rejects.toThrow();
  controller.abort(); first.resolve({ items: [calendarEvent()], total: 51 });
  await rejected;
  expect(api.getAssignmentCalendar).toHaveBeenCalledOnce();
});
it("rejects an incomplete changing calendar instead of silently dropping later events", async () => {
  api.getAssignmentCalendar.mockResolvedValueOnce({ items: [calendarEvent()], total: 2 }).mockResolvedValueOnce({ items: [], total: 2 });
  await expect(loadCalendarEvents("room", "start", "end", new AbortController().signal)).rejects.toThrow("Calendar changed");
});
it("caps crowded day chips, exposes every event, and deduplicates assignment statistics", async () => {
  const events = [calendarEvent(1, "AVAILABLE"), calendarEvent(1), calendarEvent(1, "CUTOFF"), calendarEvent(2)];
  api.getAssignmentCalendar.mockResolvedValue({ items: events, total: 4 });
  const { container } = renderWithLocale(<AssignmentCalendarPanel classroomId="room" onOpenAssignment={vi.fn()} />);
  const more = await screen.findByRole("button", { name: "+1 more events" });
  expect(container.querySelectorAll(".calendar-event-chip")).toHaveLength(3);
  fireEvent.click(more);
  const details = screen.getByRole("complementary", { name: "Selected day details" });
  expect(within(details).getAllByRole("listitem")).toHaveLength(4);
  expect(within(details).getByRole("heading", { level: 3, name: /Thursday/ })).toHaveFocus();
  expect(within(details).getByText("Scheduled assignments").nextElementSibling).toHaveTextContent("2");
  fireEvent.change(screen.getByLabelText("Event filter"), { target: { value: "CUTOFF" } });
  expect(container.querySelectorAll(".calendar-event-chip")).toHaveLength(1);
  expect(within(details).getAllByRole("listitem")).toHaveLength(1);
  expect(within(details).getByText("Scheduled assignments").nextElementSibling).toHaveTextContent("1");
  fireEvent.click(screen.getByRole("button", { name: "Week" }));
  expect(container.querySelectorAll(".calendar-day")).toHaveLength(7);
  expect(container.querySelectorAll(".calendar-event-chip")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "List" }));
  expect(container.querySelectorAll(".calendar-agenda li")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  expect(screen.getByRole("button", { name: "Danh sách" })).toHaveAttribute("aria-pressed", "true");
  expect(api.getAssignmentCalendar).toHaveBeenCalledOnce();
});
it("marks today separately from selection and supports keyboard date navigation", async () => {
  renderWithLocale(<AssignmentCalendarPanel classroomId="room" onOpenAssignment={vi.fn()} />);
  const today = screen.getByRole("button", { name: "Thursday, October 15, 2026" });
  expect(today).toHaveAttribute("aria-current", "date");
  expect(today).toHaveAttribute("aria-pressed", "true");
  fireEvent.keyDown(today, { key: "ArrowRight" });
  const next = screen.getByRole("button", { name: "Friday, October 16, 2026" });
  expect(next).toHaveFocus(); expect(next).toHaveAttribute("aria-pressed", "true");
  expect(today).toHaveAttribute("aria-current", "date"); expect(today).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(screen.getByRole("button", { name: "Week" }));
  expect(screen.getByRole("button", { name: "Friday, October 16, 2026" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  expect(screen.getByRole("button", { name: "Friday, October 23, 2026" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "Today" }));
  expect(screen.getByRole("button", { name: "Thursday, October 15, 2026" })).toHaveAttribute("aria-pressed", "true");
  await waitFor(() => expect(api.getAssignmentCalendar).toHaveBeenCalledOnce());
});
it("aborts old month requests and ignores late responses after navigating", async () => {
  const old = deferred<{ items: CalendarEvent[]; total: number }>();
  api.getAssignmentCalendar.mockReturnValueOnce(old.promise).mockResolvedValue({ items: [], total: 0 });
  renderWithLocale(<AssignmentCalendarPanel classroomId="room" onOpenAssignment={vi.fn()} />);
  await waitFor(() => expect(api.getAssignmentCalendar).toHaveBeenCalledOnce());
  const signal = api.getAssignmentCalendar.mock.calls[0][4] as AbortSignal;
  fireEvent.click(screen.getByRole("button", { name: "Next month" }));
  await waitFor(() => expect(api.getAssignmentCalendar).toHaveBeenCalledTimes(2));
  expect(signal.aborted).toBe(true);
  await act(async () => old.resolve({ items: [calendarEvent()], total: 1 }));
  expect(screen.getByRole("heading", { name: "November 2026" })).toBeInTheDocument();
  expect(screen.queryByText("Fictional lesson 0")).not.toBeInTheDocument();
});
it("shows retry on calendar failure and uses only real student progress", async () => {
  api.getAssignmentCalendar.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ items: [{ ...calendarEvent(), progress: { ...progress, submission_status: "SUBMITTED_LATE" } }], total: 1 });
  renderWithLocale(<AssignmentCalendarPanel classroomId="room" onOpenAssignment={vi.fn()} />);
  await screen.findByRole("alert"); fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await screen.findByText("Submitted late");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
