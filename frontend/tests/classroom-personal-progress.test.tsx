import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MyClassroomProgressDashboard } from "@/features/classrooms/lms/my-classroom-progress";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), progress: null as unknown }));
vi.mock("@/lib/api/classroom-learning", async original => ({ ...await original<object>(), getLearningDashboard: api.get, saveLearningGoals: api.save }));
vi.mock("@/features/classrooms/scheduling/progress-provider", () => ({ useAssignmentProgress: () => api.progress }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));
const skillNames = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;
const dashboard = { start: "2026-01-01T00:00:00Z", end: "2026-04-01T00:00:00Z", active_students: 1, assigned_activities: 99, eligible_requirements: 3, completion_rate: 100 / 3, on_time_rate: 0, counts: { SUBMITTED_LATE: 1, NOT_STARTED: 2 }, pending_human: 1, goals: { overall: 7, reading: null, listening: null, writing: null, speaking: null }, skills: skillNames.map(skill => ({ skill, sample_size: 0, independent_assessments: 0, recent_independent_assessments: 0, latest: null, average: null, recent_average: null, trends: [] })), question_types: [], criteria: [], weaknesses: [], recent_assessments: [], completion_by_assignment: [], total_completion_activities: 0, attention_students: [], recommendations: [], criteria_truncated: false };
const props = { classroomId: "room", assignments: [], isStudent: true, canAnalytics: false, onOpenAssignment: vi.fn(), onNavigate: vi.fn() };
beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); api.get.mockResolvedValue(dashboard); api.save.mockResolvedValue(dashboard.goals); api.progress = { items: {}, loading: false, error: false, staff: false, refresh: vi.fn(), assignments: [] }; });

it("loads only personal data and presents eligible and accepted counts honestly", async () => {
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  expect(await screen.findByText("Assigned to you")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledOnce();
  expect(api.get).toHaveBeenCalledWith("room", true, { completion_offset: 0 }, undefined, expect.any(AbortSignal));
  expect(screen.getByText("Assigned to you").previousElementSibling).toHaveTextContent("3");
  expect(screen.queryByText("99")).not.toBeInTheDocument();
  expect(screen.getByRole("img", { name: "1 / 3 · 33.3%" })).toBeInTheDocument();
  expect(screen.getByText("Comparable overall average unavailable")).toBeInTheDocument();
  expect(screen.getByText("No valid band results yet")).toBeInTheDocument();
  expect(document.querySelector(".personal-chart polyline")).toBeNull();
});

it("shows a null completion without a zero percent ring", async () => {
  api.get.mockResolvedValue({ ...dashboard, eligible_requirements: 0, completion_rate: null, counts: {} });
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  expect(await screen.findByText("No eligible requirements yet.")).toBeInTheDocument();
  expect(document.querySelector(".personal-completion-ring")).toBeNull();
  expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
});

it("renders real dated points by skill, with a line only for multiple observations", async () => {
  api.get.mockResolvedValue({ ...dashboard, skills: dashboard.skills.map(row => row.skill === "READING" ? { ...row, sample_size: 2, average: 6, latest: 6.5, trends: [{ attempt_id: "a", assignment_id: "a1", at: "2026-02-01T00:00:00Z", band: 5.5 }, { attempt_id: "b", assignment_id: "a2", at: "2026-03-01T00:00:00Z", band: 6.5 }] } : row.skill === "WRITING" ? { ...row, sample_size: 1, trends: [{ attempt_id: "c", assignment_id: "a3", at: "2026-02-10T00:00:00Z", band: 7 }] } : row) });
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  expect(await screen.findByRole("img", { name: /Progress over time · 3 assessment/ })).toBeInTheDocument();
  expect(document.querySelectorAll('.personal-chart g[data-skill="READING"] polyline')).toHaveLength(1);
  expect(document.querySelectorAll('.personal-chart g[data-skill="WRITING"] polyline')).toHaveLength(0);
  expect(document.querySelectorAll('.personal-chart g[data-skill="WRITING"] circle')).toHaveLength(1);
  expect(screen.getByLabelText(/Writing · .* · 7.0/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Dated assessment observations"));
  expect(screen.getByText(/Reading · 6.5/)).toBeInTheDocument();
});

it("rejects invalid dates without a request and applies valid dates", async () => {
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  await screen.findByText("Assigned to you");
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-03-05" } });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-02-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  expect(screen.getByRole("alert")).toHaveTextContent("valid date range"); expect(api.get).toHaveBeenCalledOnce();
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-05" } });
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  const range = api.get.mock.calls[1][2]; expect(Date.parse(range.end) - Date.parse(range.start)).toBe(86400000);
});

it("cancels stale requests when a new date range is applied", async () => {
  let resolveOld!: (value: unknown) => void;
  api.get.mockResolvedValueOnce(dashboard).mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce({ ...dashboard, eligible_requirements: 4 });
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  await screen.findByText("Assigned to you");
  fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-02-01" } });
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-02-10" } });
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  const oldSignal = api.get.mock.calls[1][4] as AbortSignal;
  fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-02-11" } });
  fireEvent.click(screen.getByRole("button", { name: "Show" }));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(3)); expect(oldSignal.aborted).toBe(true);
  resolveOld({ ...dashboard, eligible_requirements: 99 });
  await waitFor(() => expect(screen.getByText("Assigned to you").previousElementSibling).toHaveTextContent("4"));
  expect(screen.queryByText("99")).not.toBeInTheDocument();
});

it("uses evidence-backed recommendations and opens real assignments", async () => {
  const open = vi.fn();
  api.get.mockResolvedValue({ ...dashboard, weaknesses: [{ weakness_type: "QUESTION_TYPE", skill: "READING", category: "short_answer", observed: 30, baseline: 60, sample_size: 10, confidence_level: "MEDIUM", recommendation_reason: "LOW_RECENT_ACCURACY" }], recommendations: [{ assignment_id: "recommended", title: "Reading practice", skill: "READING", category: "short_answer", reason: "LOW_RECENT_ACCURACY" }] });
  renderWithLocale(<MyClassroomProgressDashboard {...props} onOpenAssignment={open} />);
  fireEvent.click(await screen.findByRole("button", { name: "Practice now" })); expect(open).toHaveBeenCalledWith("recommended");
  expect(screen.getByText(/Observed: 30.0%/)).toHaveTextContent("Sample size: 10");
});

it("shows actual effective upcoming deadlines, excludes archived and completed work, and opens the assignment", async () => {
  const future = new Date(Date.now() + 86400000).toISOString(), past = new Date(Date.now() - 86400000).toISOString();
  const assignment = (id: string, status: "ACTIVE" | "ARCHIVED") => ({ id, classroom_id: "room", test_version_id: "version", created_by_user_id: "teacher", title: id, note: null, status, created_at: "2026-01-01T00:00:00Z", archived_at: null });
  const assignments = [assignment("Extended", "ACTIVE"), assignment("Done", "ACTIVE"), assignment("Old", "ACTIVE"), assignment("Archived", "ARCHIVED")];
  const progress = (due: string, accepted = false) => ({ effective_due_at: due, effective_cutoff_at: null, accepted, availability_status: "SCHEDULED", submission_status: "NOT_STARTED" });
  api.progress = { items: { Extended: progress(future), Done: progress(future, true), Old: progress(past), Archived: progress(future) }, loading: false, error: false, staff: false, refresh: vi.fn(), assignments };
  const open = vi.fn(); renderWithLocale(<MyClassroomProgressDashboard {...props} assignments={assignments} onOpenAssignment={open} />);
  fireEvent.click(await screen.findByRole("button", { name: /Extended/ })); expect(open).toHaveBeenCalledWith("Extended");
  expect(screen.queryByRole("button", { name: /Done|Old|Archived/ })).not.toBeInTheDocument();
  expect(document.querySelector(`time[datetime="${future}"]`)).toBeInTheDocument();
  expect(screen.getByText(/Scheduled/)).toBeInTheDocument();
});

it("preserves goals and detailed evidence without a second analytics request", async () => {
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  fireEvent.click(await screen.findByText("Target bands · 7.0"));
  fireEvent.change(screen.getByLabelText("Reading"), { target: { value: "7.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
  await waitFor(() => expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ reading: 7.5 })));
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  fireEvent.click(await screen.findByText("Learning details"));
  expect(await screen.findByRole("heading", { name: "Question-type accuracy" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Human-final criteria" })).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledTimes(2);
});

it("retains pending human grading provenance in detailed assessment history", async () => {
  const score = { assignment_id: "assignment", root_id: "root", kind: "ATTEMPT", result_attempt_id: "root", skill: "WRITING", scope: "FOCUSED_UNIT", context: "WRITING:FOCUSED_UNIT", band: null, raw_score: null, max_score: null, provenance: "PENDING_HUMAN", finished_at: "2026-02-01T10:00:00Z", accepted: true, late: false, submission_status: "SUBMITTED_ON_TIME", mixed_context_fallback: false, breakdown: [] };
  api.get.mockResolvedValue({ ...dashboard, recent_assessments: [score] });
  renderWithLocale(<MyClassroomProgressDashboard {...props} />);
  fireEvent.click(await screen.findByText("Learning details"));
  fireEvent.click(await screen.findByText("Recent assessments (1)"));
  expect(await screen.findByText(/Score source: Awaiting human grading/)).toBeInTheDocument();
  expect(screen.getByText(/Focused practice/)).toBeInTheDocument();
});

it("does not substitute class totals for a teacher's personal progress and localizes", async () => {
  const navigate = vi.fn(); api.get.mockResolvedValue({ ...dashboard, active_students: 0, eligible_requirements: 0, completion_rate: null, counts: {} });
  renderWithLocale(<MyClassroomProgressDashboard {...props} isStudent={false} canAnalytics onNavigate={navigate} />);
  expect(await screen.findByText(/This is your personal progress/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "View classroom analytics" })); expect(navigate).toHaveBeenCalledWith("analytics");
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByText("Bài tập được giao")).toBeInTheDocument();
});
