import { act, fireEvent, screen, waitFor } from "@testing-library/react";
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

async function chooseWriting() {
  fireEvent.change(screen.getByLabelText("Test"), { target: { value: "eligible" } });
  await screen.findByLabelText("Assigned skill");
  fireEvent.change(screen.getByLabelText("Assigned skill"), { target: { value: "WRITING" } });
}

it("keeps all schedule policies in a disclosure and submits aware timestamps with the selected target", async () => {
  const changed = vi.fn().mockResolvedValue(undefined);
  const { container } = renderWithLocale(<AssignmentForm classroomId="room" tests={tests} onCreated={changed} />);
  await chooseWriting();
  const disclosure = container.querySelector("details")!;
  expect(disclosure).not.toHaveAttribute("open");
  fireEvent.click(disclosure.querySelector("summary")!);
  fireEvent.change(screen.getByLabelText("Available from"), { target: { value: "2026-11-01T09:00" } });
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-03T09:00" } });
  fireEvent.change(screen.getByLabelText("Hard cut-off"), { target: { value: "2026-11-04T09:00" } });
  fireEvent.change(screen.getByLabelText("Maximum starts"), { target: { value: "3" } });
  fireEvent.click(screen.getByLabelText("Allow late submissions"));
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  await screen.findByText("Assignment created.");
  expect(api.createAssignment).toHaveBeenCalledWith("room", expect.objectContaining({
    available_from: new Date("2026-11-01T09:00").toISOString(), due_at: new Date("2026-11-03T09:00").toISOString(), cutoff_at: new Date("2026-11-04T09:00").toISOString(), max_attempts: 3, allow_late_submission: false,
    target: { mode: "MODULE", module: "WRITING", scope: "FULL_MODULE" },
  }));
  expect(changed).toHaveBeenCalledOnce(); expect(api.refresh).not.toHaveBeenCalled();
});

it("prevents duplicate writes while pending and retries only refresh after creation succeeds", async () => {
  let finish!: (value: object) => void;
  api.createAssignment.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const changed = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  const { container } = renderWithLocale(<AssignmentForm classroomId="room" tests={tests} onCreated={changed} />);
  await chooseWriting();
  fireEvent.submit(container.querySelector("form")!); fireEvent.submit(container.querySelector("form")!);
  expect(api.createAssignment).toHaveBeenCalledOnce();
  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  await act(async () => finish({}));
  expect(await screen.findByRole("alert")).toHaveTextContent("was created");
  fireEvent.submit(container.querySelector("form")!); expect(api.createAssignment).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Retry loading" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(changed).toHaveBeenCalledTimes(2); expect(api.createAssignment).toHaveBeenCalledOnce();
});

it("preserves selected target after an API error and rejects invalid schedules before writing", async () => {
  api.createAssignment.mockRejectedValueOnce(new Error("offline"));
  const { container } = renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />);
  await chooseWriting();
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not create");
  expect(screen.getByLabelText("Assigned skill")).toHaveValue("WRITING");
  fireEvent.change(screen.getByLabelText("Due date"), { target: { value: "2026-11-03T09:00" } });
  fireEvent.change(screen.getByLabelText("Hard cut-off"), { target: { value: "2026-11-02T09:00" } });
  fireEvent.submit(container.querySelector("form")!);
  expect(screen.getByRole("alert")).toHaveTextContent("Check date ordering");
  expect(api.createAssignment).toHaveBeenCalledOnce();
});

const moduleBase = { ...detail.modules[0], writing_tasks: undefined };
const otherModules: VersionDetail["modules"] = [
  { ...moduleBase, id: "r", module_type: "READING", reading_passages: [{ id: "passage2", title: "Fictional passage", order_index: 1, question_groups: [] }] },
  { ...moduleBase, id: "l", module_type: "LISTENING", listening_sections: [{ id: "part3", title: null, order_index: 2, question_groups: [] }] },
  { ...moduleBase, id: "s", module_type: "SPEAKING", speaking_parts: [{ id: "part", part_number: 2, order_index: 1, title: null, prompts: [{ id: "prompt1", order_index: 0, prompt_type: "LONG_TURN", prompt_text: "Fictional prompt", cue_points: [] }] }] },
];

it.each([ ["READING", "passage2", "READING_PASSAGE"], ["LISTENING", "part3", "LISTENING_PART"], ["SPEAKING", "prompt1", "SPEAKING_PROMPT"] ])("uses actual %s focused-unit IDs and requires a unit selection", async (skill, id, kind) => {
  api.assignmentVersion.mockResolvedValue({ ...detail, modules: otherModules });
  renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />);
  fireEvent.change(screen.getByLabelText("Test"), { target: { value: "eligible" } }); await screen.findByLabelText("Assigned skill");
  fireEvent.change(screen.getByLabelText("Assigned skill"), { target: { value: skill } });
  fireEvent.change(screen.getByLabelText("Assignment scope"), { target: { value: "FOCUSED_UNIT" } });
  expect(screen.getByRole("button", { name: "Create assignment" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Assigned unit"), { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  await waitFor(() => expect(api.createAssignment).toHaveBeenCalledWith("room", expect.objectContaining({ target: { mode: "MODULE", module: skill, scope: "FOCUSED_UNIT", focused_unit: { id, kind } } })));
});

it("offers Full Mock only when every actual module has a valid duration", async () => {
  api.assignmentVersion.mockResolvedValue({ ...detail, modules: [...detail.modules, ...otherModules] });
  renderWithLocale(<AssignmentForm classroomId="room" tests={tests} />);
  fireEvent.change(screen.getByLabelText("Test"), { target: { value: "eligible" } }); await screen.findByLabelText("Assigned skill");
  expect(screen.getByRole("option", { name: "Full Mock" })).toBeEnabled();
  fireEvent.change(screen.getByLabelText("Assigned skill"), { target: { value: "FULL_MOCK" } });
  expect(screen.queryByLabelText("Assigned unit")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Create assignment" }));
  await waitFor(() => expect(api.createAssignment).toHaveBeenCalledWith("room", expect.objectContaining({ target: { mode: "FULL_MOCK" } })));
});
