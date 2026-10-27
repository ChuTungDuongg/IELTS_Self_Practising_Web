import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { ClassworkPanel } from "@/features/classrooms/content/classwork-panel";
import { ClassroomWorkspace } from "@/features/classrooms/content/classroom-workspace";
import { LearningAnalyticsPanel } from "@/features/classrooms/lms/learning-analytics";
import { LearningPlansPanel } from "@/features/classrooms/lms/learning-plans";
import { GradebookPanel } from "@/features/classrooms/lms/gradebook";
import { goalsSchema } from "@/lib/api/classroom-learning";
import { ActionMenu } from "@/features/classrooms/lms/action-menu";
import { ContentAction } from "@/features/classrooms/content/content-action";

const api = vi.hoisted(() => ({ getClasswork: vi.fn(), listFeed: vi.fn(), getLearningDashboard: vi.fn(), getLearningPlans: vi.fn(), saveLearningGoals: vi.fn(), completePlanResource: vi.fn(), saveLearningPlan: vi.fn(), getGradebook: vi.fn() }));
vi.mock("@/lib/api/classroom-content", async original => ({ ...await original<object>(), getClasswork: api.getClasswork, listFeed: api.listFeed }));
vi.mock("@/lib/api/classroom-learning", async original => ({ ...await original<object>(), ...api }));
vi.mock("@/lib/api/classroom-lms", async original => ({ ...await original<object>(), getGradebook: api.getGradebook }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
const empty = { revision: 0, sections: [], resources: [], items: [] };
const room = { id: "room", teacher_id: "teacher", name: "Evening IELTS", description: null, status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
const goals = { overall: 7, reading: null, listening: null, writing: null, speaking: null };
const dashboard = { start: "2026-10-01T00:00:00Z", end: "2026-10-27T00:00:00Z", active_students: 1, assigned_activities: 0, eligible_requirements: 0, completion_rate: null, on_time_rate: null, counts: {}, pending_human: 0, goals, skills: ["READING", "LISTENING", "WRITING", "SPEAKING"].map(skill => ({ skill, sample_size: 0, independent_assessments: 0, recent_independent_assessments: 0, latest: null, average: null, recent_average: null, trends: [] })), question_types: [], criteria: [], weaknesses: [], recent_assessments: [], completion_by_assignment: [], total_completion_activities: 0, attention_students: [], recommendations: [], criteria_truncated: false };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); api.getClasswork.mockResolvedValue(empty); api.listFeed.mockResolvedValue({ items: [], next_cursor: null }); api.getLearningDashboard.mockResolvedValue(dashboard); api.getLearningPlans.mockResolvedValue({ items: [], total: 0 }); api.saveLearningGoals.mockResolvedValue(goals); });

it("keeps Classwork forms closed until a content action is chosen and handles no eligible assignments", () => {
  const create = vi.fn(); renderWithLocale(<ClassworkPanel classroomId="room" data={empty} assignments={[]} canAuthor onRefresh={vi.fn()} onChange={vi.fn()} onOpenAssignment={vi.fn()} onCreateAssignment={create} />);
  expect(screen.queryByLabelText("Topic name")).not.toBeInTheDocument(); expect(screen.queryByLabelText("Choose an assignment")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Add content")); fireEvent.click(screen.getByRole("button", { name: "Add assignment to a topic" }));
  expect(screen.getByText(/No active assignments are available/)).toBeInTheDocument(); expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" })); expect(create).toHaveBeenCalledOnce();
});

it("opens a topic editor from the role-aware header menu with Vietnamese terminology", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={room} user={{ id: "teacher", role: "TEACHER" }} assignments={[]} canManage />);
  await screen.findByText("No classroom updates yet."); fireEvent.click(screen.getByText("Create")); fireEvent.click(screen.getByRole("button", { name: "Create topic" }));
  expect(await screen.findByLabelText("Topic name")).toHaveFocus(); expect(screen.getByRole("tab", { name: "Classwork" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByText("Switch to Vietnamese")); expect(screen.getByLabelText("Tên chủ đề")).toBeInTheDocument(); expect(screen.queryByText("Phần học")).not.toBeInTheDocument();
});

it("enforces Analytics capability in navigation while every user retains My Progress", async () => {
  renderWithLocale(<ClassroomWorkspace classroom={{ ...room, capabilities: ["grades.view", "grades.edit"] }} user={{ id: "ta", role: "USER" }} assignments={[]} canManage />);
  expect(screen.getByRole("tab", { name: "Gradebook" })).toBeInTheDocument(); expect(screen.queryByRole("tab", { name: "Analytics" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "My Progress" })); await waitFor(() => expect(api.getLearningDashboard).toHaveBeenCalledWith("room", true, { completion_offset: 0 }, undefined, expect.any(AbortSignal)));
  expect(api.getLearningPlans).toHaveBeenCalledWith("room", "ta", 0, expect.any(AbortSignal));
});

it("shows insufficient data without a fabricated chart and persists personal targets", async () => {
  renderWithLocale(<LearningAnalyticsPanel classroomId="room" own onOpenAssignment={vi.fn()} />);
  await screen.findByText("Target bands · 7.0"); expect(screen.queryByRole("img")).not.toBeInTheDocument(); expect(screen.getAllByText("Not enough completed assessments.").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByText("Target bands · 7.0")); fireEvent.change(screen.getByLabelText("Reading"), { target: { value: "7.5" } }); fireEvent.click(screen.getByRole("button", { name: "Save targets" }));
  await waitFor(() => expect(api.saveLearningGoals).toHaveBeenCalledWith({ ...goals, reading: 7.5 }));
  expect(goalsSchema.parse(goals).overall).toBe(7);
});

it("shows errors and supports retrying analytics without displaying stale results", async () => {
  api.getLearningDashboard.mockRejectedValueOnce(new Error("offline")); renderWithLocale(<LearningAnalyticsPanel classroomId="room" own onOpenAssignment={vi.fn()} />);
  expect(await screen.findByRole("alert")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Retry" })); expect(await screen.findByText("Target bands · 7.0")).toBeInTheDocument();
});

it("opens real recommendations and shows evidence beside weaknesses", async () => {
  api.getLearningDashboard.mockResolvedValue({ ...dashboard, weaknesses: [{ weakness_type: "QUESTION_TYPE", skill: "READING", category: "short_answer", evidence: "10 questions", sample_size: 10, severity: "HIGH", confidence_level: "MEDIUM", recommendation_reason: "LOW_RECENT_ACCURACY", observed: 30, baseline: 60 }], recommendations: [{ assignment_id: "a", title: "Next reading practice", skill: "READING", category: "short_answer", reason: "LOW_RECENT_ACCURACY", href: "/classrooms/room?assignment=a" }] });
  const open = vi.fn(); renderWithLocale(<LearningAnalyticsPanel classroomId="room" own onOpenAssignment={open} />); fireEvent.click(await screen.findByRole("button", { name: "Next reading practice" })); expect(open).toHaveBeenCalledWith("a"); expect(screen.getByText(/Observed: 30.0%/)).toHaveTextContent("Sample size: 10");
});

it("allows only resource markers and keeps exam completion tied to accepted submissions", async () => {
  api.getLearningPlans.mockResolvedValue({ total: 1, items: [{ id: "p", student_id: "s", title: "Reading focus", target_skill: "READING", focus_area: "Review", description: null, status: "ACTIVE", revision: 1, completed_items: 0, items: [{ id: "r", title: "Strategy notes", resource_id: "resource", assignment_id: null, available: true, completed: false, completion_source: "NONE" }, { id: "a", title: "Assessment", resource_id: null, assignment_id: "assignment", available: true, completed: false, completion_source: "NONE" }] }] });
  renderWithLocale(<LearningPlansPanel classroomId="room" own assignments={[]} classwork={empty} onOpenAssignment={vi.fn()} />);
  const mark = await screen.findByRole("button", { name: "Mark resource task complete" }); expect(screen.getAllByRole("button", { name: "Mark resource task complete" })).toHaveLength(1); fireEvent.click(mark); await waitFor(() => expect(api.completePlanResource).toHaveBeenCalledWith("room", "p", "r")); expect(screen.queryByRole("button", { name: "Create improvement plan" })).not.toBeInTheDocument();
});

it("offers an accessible student-list alternative to the gradebook matrix", async () => {
  api.getGradebook.mockResolvedValue({ assignments: [], students: [{ student_id: "s", display_name: "Mina", active_member: true, cells: [] }], total_students: 1, total_assignments: 0 });
  renderWithLocale(<GradebookPanel classroomId="room" assignments={[]} canEdit={false} />); fireEvent.click(await screen.findByRole("button", { name: "Student list" })); expect(screen.queryByRole("table")).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "Mina" })).toBeInTheDocument();
});

it("keeps destructive confirmation visible inside an action menu and restores keyboard focus", () => {
  const action = vi.fn(); renderWithLocale(<ActionMenu label="Topic actions"><ContentAction action={action} confirm={{ title: "Archive topic?", description: "Retain classroom history." }}>Archive</ContentAction></ActionMenu>);
  fireEvent.click(screen.getByText("Topic actions")); fireEvent.click(screen.getByRole("button", { name: "Archive" })); expect(screen.getByText("Topic actions").closest("details")).toHaveAttribute("open"); expect(screen.getByRole("dialog")).toBeInTheDocument(); expect(action).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" })); fireEvent.keyDown(screen.getByText("Topic actions"), { key: "Escape" }); expect(screen.getByText("Topic actions").closest("details")).not.toHaveAttribute("open"); expect(screen.getByText("Topic actions")).toHaveFocus();
});
