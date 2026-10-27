import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { AssignmentForm } from "@/features/classrooms/assignment-form";
import { AssignmentList } from "@/features/classrooms/assignment-list";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";

const api = vi.hoisted(() => ({ assignmentVersion: vi.fn(), createAssignment: vi.fn(), startAssignment: vi.fn(), push: vi.fn(), refresh: vi.fn() }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), ...api }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push, refresh: api.refresh }) }));
const detail: VersionDetail = { id: "eligible", test_id: "test", test_title: "Fictional assessment", version_number: 2, status: "PUBLISHED", created_at: "now", published_at: "now", modules: [{ id: "m", module_type: "WRITING", title: null, recommended_duration_seconds: 3600, passage_count: 0, listening_part_count: 0, writing_task_count: 1, question_count: 0, writing_tasks: [{ id: "task2", task_number: 2, task_type: null, prompt_excerpt: null, minimum_recommended_words: 250, recommended_duration_seconds: 2400 }] }] };
const tests: TestSummary[] = [{ id: "test", title: "Fictional assessment", description: null, source_label: null, test_number: null, archived_at: null, created_at: "now", updated_at: "now", versions: [{ id: "old", version_number: 1, status: "PUBLISHED", created_at: "now", published_at: "now" }, { id: "eligible", version_number: 2, status: "PUBLISHED", created_at: "now", published_at: "now" }, { id: "draft", version_number: 3, status: "DRAFT", created_at: "now", published_at: null }] }];
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); api.assignmentVersion.mockResolvedValue(detail); api.createAssignment.mockResolvedValue({}); api.startAssignment.mockResolvedValue({ attempt_id: "attempt", test_session_id: null }); });

it("selects one eligible published revision by Test identity and hides technical numbering", async () => {
  renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />);
  const select = screen.getByLabelText("Test"); expect(select.querySelectorAll("option")).toHaveLength(2); expect(screen.queryByText(/Version [123]/)).not.toBeInTheDocument();
  fireEvent.change(select, { target: { value: "eligible" } });
  await waitFor(() => expect(api.assignmentVersion).toHaveBeenCalledWith("room", "eligible", expect.any(AbortSignal)));
  expect(await screen.findByLabelText("Assigned skill")).toHaveValue(""); expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled();
});
it("creates a focused Writing Task 2 assignment from real version metadata", async () => {
  renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />);
  fireEvent.change(screen.getByLabelText("Test"), { target: { value: "eligible" } }); await screen.findByLabelText("Assigned skill");
  fireEvent.change(screen.getByLabelText("Assigned skill"), { target: { value: "WRITING" } }); fireEvent.change(screen.getByLabelText("Assignment scope"), { target: { value: "FOCUSED_UNIT" } });
  fireEvent.change(screen.getByLabelText("Assigned unit"), { target: { value: "task2" } }); fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  await waitFor(() => expect(api.createAssignment).toHaveBeenCalledWith("room", expect.objectContaining({ test_version_id: "eligible", target: { mode: "MODULE", module: "WRITING", scope: "FOCUSED_UNIT", focused_unit: { kind: "WRITING_TASK", id: "task2" } } })));
});
it("shows only valid skills and explains unavailable Full Mock", async () => {
  renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />); fireEvent.change(screen.getByLabelText("Test"), { target: { value: "eligible" } }); await screen.findByLabelText("Assigned skill");
  expect(screen.queryByRole("option", { name: "Reading" })).not.toBeInTheDocument(); expect(screen.getByRole("option", { name: "Full Mock" })).toBeDisabled(); expect(screen.getByText(/needs all four skills/)).toBeInTheDocument();
});
it("starts a targeted assignment without allowing unrelated skill or unit selection", async () => {
  renderWithLocale(<AssignmentList assignments={[{ id: "a", classroom_id: "room", test_version_id: "eligible", created_by_user_id: "teacher", title: "Fictional homework", note: null, status: "ACTIVE", created_at: "now", archived_at: null, version: detail, target: { mode: "MODULE", module: "WRITING", scope: "FOCUSED_UNIT", focused_unit: { kind: "WRITING_TASK", id: "task2" } } }]} />);
  expect(screen.getByText(/Writing.*Task 2/)).toBeInTheDocument(); expect(screen.queryByLabelText("Start mode")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Start assignment" }));
  await waitFor(() => expect(api.startAssignment).toHaveBeenCalledWith("a", expect.objectContaining({ module: "WRITING", scope: "FOCUSED_UNIT", focused_unit: { kind: "WRITING_TASK", id: "task2" } })));
  expect(api.push).toHaveBeenCalledWith("/attempt/attempt");
});
