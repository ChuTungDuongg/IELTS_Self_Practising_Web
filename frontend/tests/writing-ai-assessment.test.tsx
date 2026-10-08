import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingAIAssessment } from "@/features/writing/writing-ai-assessment";
import { WritingReviewView } from "@/features/writing/writing-review";
import { createAIWritingRun, getAIWritingRun, listAIWritingRuns, watchAIWritingRun, type AIWritingRun } from "@/lib/api/writing-ai";
import { saveWritingTaskScore, type WritingReviewPayload } from "@/lib/api/exam";
import { ApiError } from "@/lib/api/client";

const auth = vi.hoisted(() => ({ role: "ADMIN" }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { role: auth.role } }) }));
vi.mock("@/lib/api/writing-ai", async (original) => ({ ...await original<typeof import("@/lib/api/writing-ai")>(), listAIWritingRuns: vi.fn(), createAIWritingRun: vi.fn(), getAIWritingRun: vi.fn() }));
vi.mock("@/lib/api/exam", async (original) => ({ ...await original<typeof import("@/lib/api/exam")>(), saveWritingTaskScore: vi.fn() }));

const attemptId = "11111111-1111-4111-8111-111111111111";
const taskId = "22222222-2222-4222-8222-222222222222";
const runId = "33333333-3333-4333-8333-333333333333";
const criterion = { score: 6.5, feedback: "Develop examples.", strengths: ["Clear position."], improvements: ["Explain supporting details."], evidence: [{ quote: "Fictional parks help.", assessment: "Relevant position." }] };
const result = { criteria: { ta: criterion, cc: { ...criterion, score: 6 }, lr: { ...criterion, score: 7 }, gra: { ...criterion, score: 6 } }, raw_mean: 6.375, overall_band: 6.5 };
const pending: AIWritingRun = { id: runId, attempt_id: attemptId, writing_task_id: taskId, status: "PENDING", provider: "fake", model: "fictional", prompt_version: "v1", result: null, progress: {}, error_code: null, error_message: null, started_at: null, completed_at: null, created_at: "2026-10-08T00:00:00Z" };
const completed: AIWritingRun = { ...pending, status: "COMPLETED", result, progress: result.criteria };

class MockEventSource {
  static instances: MockEventSource[] = [];
  listeners = new Map<string, (message: MessageEvent) => void>();
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string, public options: EventSourceInit) { MockEventSource.instances.push(this); }
  addEventListener(type: string, callback: (message: MessageEvent) => void) { this.listeners.set(type, callback); }
  emit(type: string, sequence: number, payload = {}) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify({ sequence, event_type: type, payload }) }));
  }
}

function panel() { return render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} hasEssay canCopy onCopy={vi.fn()} />); }
function review(): WritingReviewPayload {
  const now = "2026-10-08T00:00:00Z";
  return {
    review: { attempt: { attempt_id: attemptId, test_version_id: taskId, module: "WRITING", status: "SUBMITTED", finished_reason: "USER_SUBMIT", timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: now, last_active_at: now, finished_at: now, paused_at: null, total_paused_seconds: 0, deadline_at: null, elapsed_seconds: 100, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: now }, test_title: "Fictional review", answers: [], writing_responses: [], highlights: [], flags: [] },
    tasks: [1, 2].map((number) => ({ writing_task_id: number === 2 ? taskId : runId, task_number: number, prompt: "Fictional prompt.", image_asset_id: null, image_asset: null, minimum_recommended_words: 250, recommended_duration_seconds: 2400, content: "Fictional parks help.", word_count: 3, score: null })),
    task1_overall: null, task2_overall: null, weighted_overall: null, band_score: null,
  };
}

describe("Task 2 AI assessment", () => {
  beforeEach(() => {
    vi.clearAllMocks(); auth.role = "ADMIN"; MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify(completed), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [] });
    vi.mocked(createAIWritingRun).mockResolvedValue({ run_id: runId, cache_hit: false, existing_active: false });
    vi.mocked(getAIWritingRun).mockResolvedValue(pending);
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("starts grading and renders validated SSE trace and criterion progress", async () => {
    const rendered = panel();
    const grade = await screen.findByRole("button", { name: "Grade Task 2 with AI" });
    await waitFor(() => expect(grade).toBeEnabled());
    fireEvent.click(grade);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(createAIWritingRun).toHaveBeenCalledWith(attemptId, taskId, false);
    const source = MockEventSource.instances[0];
    expect(source.options.withCredentials).toBe(true);
    expect(source.url).toContain(`/ai-writing-grading-runs/${runId}/events?after=0`);
    act(() => source.emit("criterion.started", 2, { criterion: "ta" }));
    expect(screen.getByText("Analyzing Task Response…")).toBeInTheDocument();
    act(() => source.emit("criterion.evidence.completed", 3, { criterion: "ta", evidence: criterion.evidence }));
    expect(screen.getByText("✓ Evidence collected")).toBeInTheDocument();
    expect(screen.getByText("Fictional parks help.")).toBeInTheDocument();
    act(() => source.emit("criterion.completed", 5, { criterion: "ta", result: criterion }));
    expect(screen.getByText("✓ Task Response — 6.5")).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "AI Task Response" });
    expect(within(card).getByText("Develop examples.")).toBeInTheDocument();
    expect(within(card).getByText("Clear position.")).toBeInTheDocument();
    expect(screen.queryByText("Task Achievement")).not.toBeInTheDocument();
    rendered.unmount();
    expect(source.close).toHaveBeenCalled();
  });

  it("renders backend overall after run completion and closes the stream", async () => {
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    vi.mocked(getAIWritingRun).mockResolvedValue(completed);
    act(() => MockEventSource.instances[0].emit("run.completed", 18));
    expect(await screen.findByText(/AI Task 2 Overall:/)).toHaveTextContent("6.5");
    expect(MockEventSource.instances[0].close).toHaveBeenCalled();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });

  it("restores cached completed results without starting inference", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    panel();
    expect(await screen.findByText(/AI Task 2 Overall:/)).toHaveTextContent("6.5");
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(createAIWritingRun).not.toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("shows a retryable failed state and explicitly forces a regrade", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [{ ...pending, status: "FAILED", error_code: "PROVIDER_TIMEOUT", error_message: "AI grading timed out. Please regrade." }] });
    panel();
    expect(await screen.findByRole("alert")).toHaveTextContent("timed out");
    fireEvent.click(screen.getByRole("button", { name: "Regrade with AI" }));
    await waitFor(() => expect(createAIWritingRun).toHaveBeenCalledWith(attemptId, taskId, true));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
  });

  it("restores the latest usable assessment when a newer run failed", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [{ ...pending, id: taskId, status: "FAILED" }, completed] });
    panel();
    expect(await screen.findByText(/AI Task 2 Overall:/)).toHaveTextContent("6.5");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(createAIWritingRun).not.toHaveBeenCalled();
  });

  it("fails gracefully when AI is disabled or the start endpoint is unconfigured", async () => {
    vi.mocked(createAIWritingRun).mockRejectedValue(new ApiError("AI_NOT_CONFIGURED", "AI grading is not configured.", 503));
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("AI grading is not configured");
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("copies into the human form without saving, and leaves values editable", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    render(<WritingReviewView data={review()} />);
    expect(screen.queryByRole("button", { name: "Grade Task 2 with AI" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Copy AI suggestions to grading form" }));
    expect(screen.getByLabelText("Task 2 TA")).toHaveValue("6.5");
    expect(screen.getByLabelText("Task 2 CC")).toHaveValue("6.0");
    expect(screen.getByLabelText("Task 2 LR")).toHaveValue("7.0");
    expect(screen.getByLabelText("Task 2 GRA")).toHaveValue("6.0");
    expect(screen.getByLabelText("Task 2 TA feedback")).toHaveValue("Develop examples.");
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(screen.getByText("Waiting for all 8 criterion scores")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Task 2 TA"), { target: { value: "7.0" } });
    vi.mocked(saveWritingTaskScore).mockResolvedValue(review());
    fireEvent.click(screen.getByRole("button", { name: "Save Task 2 scores" }));
    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskId, expect.objectContaining({ ta: 7, cc: 6, lr: 7, gra: 6, ta_feedback: "Develop examples." })));
  });

  it("does not offer copying for a user without manual grading permission", async () => {
    auth.role = "USER";
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    render(<WritingReviewView data={review()} />);
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    await screen.findByText(/AI Task 2 Overall:/);
    expect(screen.queryByRole("button", { name: "Copy AI suggestions to grading form" })).not.toBeInTheDocument();
  });

  it("never adds AI controls to Task 1", () => {
    const data = review(); data.tasks = data.tasks.filter((task) => task.task_number === 1);
    render(<WritingReviewView data={data} />);
    expect(screen.queryByLabelText("AI Assessment")).not.toBeInTheDocument();
    expect(listAIWritingRuns).not.toHaveBeenCalled();
  });

  it("reconnects with the last persisted sequence and ignores replay duplicates", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify(pending), { status: 200 })));
    const callbacks = { event: vi.fn(), snapshot: vi.fn(), error: vi.fn() };
    const stop = watchAIWritingRun(runId, callbacks);
    const first = MockEventSource.instances[0];
    first.emit("criterion.started", 2, { criterion: "ta" });
    first.emit("criterion.started", 2, { criterion: "ta" });
    expect(callbacks.event).toHaveBeenCalledTimes(1);
    first.onerror?.();
    await vi.advanceTimersByTimeAsync(1600);
    expect(callbacks.snapshot).toHaveBeenCalledWith(pending);
    expect(MockEventSource.instances[1].url).toContain("after=2");
    stop();
    expect(MockEventSource.instances[1].close).toHaveBeenCalled();
  });

  it("shows an SSE failure after restoring the safe run snapshot", async () => {
    const failed = { ...pending, status: "FAILED", error_code: "INVALID_PROVIDER_OUTPUT", error_message: "The AI provider returned an invalid assessment. Please regrade." };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => new Response(JSON.stringify(failed), { status: 200 })));
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    act(() => MockEventSource.instances[0].emit("run.failed", 3, { error_code: failed.error_code, error_message: failed.error_message }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Regrade with AI" })).toBeEnabled());
    expect(screen.getByRole("alert")).toHaveTextContent("invalid assessment");
  });
});
