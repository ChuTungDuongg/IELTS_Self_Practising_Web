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
const criterion = { score: 6.5, feedback: "Cần phát triển ví dụ cụ thể.", strengths: ["Lập trường rõ ràng."], improvements: ["Giải thích chi tiết hỗ trợ."], evidence: [{ quote: "Fictional parks help.", assessment: "Luận điểm trực tiếp trả lời đề bài." }] };
const result = { criteria: { ta: criterion, cc: { ...criterion, score: 6 }, lr: { ...criterion, score: 7 }, gra: { ...criterion, score: 6 } }, raw_mean: 6.375, overall_band: 6.5 };
const pending: AIWritingRun = { id: runId, attempt_id: attemptId, writing_task_id: taskId, status: "PENDING", provider: "fake", model: "fictional", prompt_version: "mts-task2-v2", result: null, progress: {}, error_code: null, error_message: null, started_at: null, completed_at: null, created_at: "2026-10-08T00:00:00Z" };
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
    const grade = await screen.findByRole("button", { name: "Chấm Task 2 với AI" });
    await waitFor(() => expect(grade).toBeEnabled());
    fireEvent.click(grade);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(createAIWritingRun).toHaveBeenCalledWith(attemptId, taskId, false);
    const source = MockEventSource.instances[0];
    expect(source.options.withCredentials).toBe(true);
    expect(source.url).toContain(`/ai-writing-grading-runs/${runId}/events?after=0`);
    act(() => source.emit("provider.starting", 1));
    expect(screen.getByText("Đang khởi động mô hình AI…")).toBeInTheDocument();
    act(() => source.emit("provider.ready", 2));
    expect(screen.queryByText("Đang khởi động mô hình AI…")).not.toBeInTheDocument();
    act(() => source.emit("criterion.started", 3, { criterion: "ta" }));
    expect(within(screen.getByLabelText("Tiến trình Task Response")).getByText("Đang chuẩn bị…")).toBeInTheDocument();
    act(() => source.emit("criterion.evidence.completed", 4, { criterion: "ta", evidence: criterion.evidence }));
    expect(screen.getByText("✓ Đã thu thập dẫn chứng")).toBeInTheDocument();
    act(() => source.emit("criterion.completed", 5, { criterion: "ta", result: criterion }));
    expect(screen.getByText("1 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "AI Task Response" });
    expect(within(card).getByText("Cần phát triển ví dụ cụ thể.")).toBeInTheDocument();
    expect(within(card).getByText("Lập trường rõ ràng.")).toBeInTheDocument();
    expect(within(card).getByText("Fictional parks help.")).toBeInTheDocument();
    expect(within(card).getByText("Luận điểm trực tiếp trả lời đề bài.")).toBeInTheDocument();
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
    expect(await screen.findByRole("alert")).toHaveTextContent("thời gian cho phép");
    fireEvent.click(screen.getByRole("button", { name: "Chấm lại với AI" }));
    await waitFor(() => expect(createAIWritingRun).toHaveBeenCalledWith(attemptId, taskId, true));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
  });

  it("restores the latest failed run and keeps completed history available", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [{ ...pending, id: taskId, status: "FAILED" }, completed] });
    panel();
    expect(await screen.findByRole("alert")).toHaveTextContent("Các tiêu chí đã hoàn thành vẫn được giữ lại");
    expect(screen.queryByText(/AI Task 2 Overall:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /6.5 · mts-task2-v2/ }));
    expect(screen.getByText(/AI Task 2 Overall:/)).toHaveTextContent("6.5");
    expect(createAIWritingRun).not.toHaveBeenCalled();
  });

  it("fails gracefully when AI is disabled or the start endpoint is unconfigured", async () => {
    vi.mocked(createAIWritingRun).mockRejectedValue(new ApiError("AI_NOT_CONFIGURED", "AI grading is not configured.", 503));
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Chấm AI chưa được cấu hình");
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("copies into the human form without saving, and leaves values editable", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    render(<WritingReviewView data={review()} />);
    expect(screen.queryByLabelText("AI Assessment")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" }));
    expect(screen.getByLabelText("Task 2 TA")).toHaveValue("6.5");
    expect(screen.getByLabelText("Task 2 CC")).toHaveValue("6.0");
    expect(screen.getByLabelText("Task 2 LR")).toHaveValue("7.0");
    expect(screen.getByLabelText("Task 2 GRA")).toHaveValue("6.0");
    expect(screen.getByLabelText("Task 2 TA feedback")).toHaveValue(criterion.feedback);
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(screen.getByText("Waiting for all 8 criterion scores")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Task 2 TA"), { target: { value: "7.0" } });
    vi.mocked(saveWritingTaskScore).mockResolvedValue(review());
    fireEvent.click(screen.getByRole("button", { name: "Save Task 2 scores" }));
    await waitFor(() => expect(saveWritingTaskScore).toHaveBeenCalledWith(attemptId, taskId, expect.objectContaining({ ta: 7, cc: 6, lr: 7, gra: 6, ta_feedback: criterion.feedback })));
  });

  it("does not offer copying for a user without manual grading permission", async () => {
    auth.role = "USER";
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    render(<WritingReviewView data={review()} />);
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    await screen.findByText(/AI Task 2 Overall:/);
    expect(screen.queryByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" })).not.toBeInTheDocument();
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
    first.emit("heartbeat", 3);
    expect(callbacks.event).toHaveBeenCalledTimes(1);
    first.onerror?.();
    await vi.advanceTimersByTimeAsync(1600);
    expect(callbacks.snapshot).toHaveBeenCalledWith(pending);
    expect(MockEventSource.instances[1].url).toContain("after=3");
    MockEventSource.instances[1].emit("criterion.started", 2, { criterion: "ta" });
    expect(callbacks.event).toHaveBeenCalledTimes(1);
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
    await waitFor(() => expect(screen.getByRole("button", { name: "Chấm lại với AI" })).toBeEnabled());
    expect(screen.getByRole("alert")).toHaveTextContent("dữ liệu chưa hợp lệ");
  });

  it("shows semantic stages, immediate cards, 2/4, targeted retry and failure before JSON reconciliation", async () => {
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    expect(screen.getByText("0 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
    expect(screen.getAllByText("Đang chờ")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const source = MockEventSource.instances[0];
    act(() => source.emit("evidence.request.started", 1, { criterion: "ta", stage: "evidence" }));
    const ta = screen.getByLabelText("Tiến trình Task Response");
    expect(ta).toHaveAttribute("data-state", "ACTIVE");
    expect(within(ta).getByText("Đang thu thập dẫn chứng…")).toBeInTheDocument();
    act(() => source.emit("evidence.validation.started", 2, { criterion: "ta", stage: "evidence" }));
    expect(within(ta).getByText("Đang kiểm tra dẫn chứng…")).toBeInTheDocument();
    act(() => source.emit("criterion.scoring.started", 3, { criterion: "ta", stage: "scoring" }));
    expect(within(ta).getByText("Đang chấm điểm…")).toBeInTheDocument();
    act(() => source.emit("criterion.completed", 4, { criterion: "ta", result: criterion }));
    expect(screen.getByRole("article", { name: "AI Task Response" })).toBeInTheDocument();
    expect(screen.queryByText(/AI Task 2 Overall:/)).not.toBeInTheDocument();
    act(() => source.emit("criterion.completed", 5, { criterion: "cc", result: result.criteria.cc }));
    expect(screen.getByText("2 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
    act(() => source.emit("criterion.retrying", 6, { criterion: "lr", stage: "evidence" }));
    const lr = screen.getByLabelText("Tiến trình Lexical Resource");
    expect(lr).toHaveAttribute("data-state", "RETRYING");
    expect(within(lr).getByText("Đang sửa dữ liệu dẫn chứng · thử lại 1 lần…")).toBeInTheDocument();
    // Snapshot unavailable: terminal SSE must immediately override transient UI.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    act(() => source.emit("run.failed", 7, { criterion: "lr", stage: "evidence", error_code: "AI_PROVIDER_BAD_RESPONSE" }));
    expect(lr).toHaveAttribute("data-state", "FAILED");
    expect(within(lr).getByText("Không thể hoàn tất tiêu chí này.")).toBeInTheDocument();
    expect(screen.getByLabelText("Tiến trình Grammatical Range & Accuracy")).toHaveTextContent("Chưa thực hiện");
    expect(screen.queryByText(/Đang (thu thập|kiểm tra|chấm điểm|sửa dữ liệu)/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("dữ liệu chưa hợp lệ"));
  });

  it("restores a partial failed timeline with safe Vietnamese messaging and keeps old history", async () => {
    const failed: AIWritingRun = { ...pending, status: "FAILED", progress: { ta: criterion, cc: result.criteria.cc }, error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "raw details must not render", activity: { phase: "failed", criterion: "lr", stage: "evidence", started_at: pending.created_at } };
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [failed, { ...completed, id: taskId, prompt_version: "mts-task2-v1" }] });
    panel();
    await screen.findByRole("alert");
    expect(screen.getByText("2 / 4 tiêu chí hoàn tất")).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
    expect(screen.getByLabelText("Tiến trình Grammatical Range & Accuracy")).toHaveTextContent("Chưa thực hiện");
    expect(screen.queryByText("raw details must not render")).not.toBeInTheDocument();
    expect(screen.queryByText(/AI Task 2 Overall:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /6.5 · mts-task2-v1/ }));
    expect(screen.getByText(/Bản chấm cũ/)).toBeInTheDocument();
    expect(screen.getByText(/AI Task 2 Overall:/)).toHaveTextContent("6.5");
    expect(createAIWritingRun).not.toHaveBeenCalled();
  });

  it("keeps completed cards through disconnect, snapshot reconciliation and replay", async () => {
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const first = MockEventSource.instances[0];
    act(() => first.emit("criterion.completed", 5, { criterion: "ta", result: criterion }));
    const saved: AIWritingRun = { ...pending, status: "RUNNING", progress: { ta: criterion }, activity: { phase: "collecting_evidence", criterion: "cc", stage: "evidence", started_at: pending.created_at } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(saved), { status: 200 })));
    act(() => first.onerror?.());
    await waitFor(() => expect(screen.getByLabelText("Tiến trình Coherence & Cohesion")).toHaveAttribute("data-state", "ACTIVE"));
    expect(screen.getByRole("article", { name: "AI Task Response" })).toBeInTheDocument();
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(2), { timeout: 3000 });
    expect(MockEventSource.instances[1].url).toContain("after=5");
    act(() => MockEventSource.instances[1].emit("criterion.started", 4, { criterion: "ta" }));
    expect(screen.getByLabelText("Tiến trình Coherence & Cohesion")).toHaveAttribute("data-state", "ACTIVE");
    expect(createAIWritingRun).toHaveBeenCalledTimes(1);
  });

  it("keeps LR failure local, runs Grammar live, and restores failed criteria on reload", async () => {
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const source = MockEventSource.instances[0];
    act(() => source.emit("criterion.completed", 1, { criterion: "ta", result: criterion }));
    act(() => source.emit("criterion.completed", 2, { criterion: "cc", result: result.criteria.cc }));
    act(() => source.emit("criterion.failed", 3, { criterion: "lr", stage: "evidence", error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "private error must not render" }));
    expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("private error must not render")).not.toBeInTheDocument();
    act(() => source.emit("criterion.started", 4, { criterion: "gra" }));
    expect(screen.getByText("2 hoàn tất · 1 lỗi · 1 đang chấm")).toBeInTheDocument();
    expect(screen.getByText("Đang chấm bài…")).toBeInTheDocument();
    expect(screen.getByLabelText("Tiến trình Grammatical Range & Accuracy")).toHaveAttribute("data-state", "ACTIVE");
    const visible = screen.getByLabelText("Scoring Trace").textContent;
    act(() => source.emit("heartbeat", 5));
    expect(screen.getByLabelText("Scoring Trace").textContent).toBe(visible);
    act(() => source.emit("criterion.completed", 6, { criterion: "gra", result: criterion }));
    expect(screen.getByRole("article", { name: "AI Grammatical Range & Accuracy" })).toBeInTheDocument();
    const failed: AIWritingRun = { ...pending, status: "FAILED", error_code: "AI_PROVIDER_BAD_RESPONSE", progress: { ta: criterion, cc: criterion, gra: criterion }, failures: { lr: { error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "Không thể hoàn tất tiêu chí này.", stage: "evidence" } } };
    vi.mocked(getAIWritingRun).mockResolvedValue(failed);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(failed), { status: 200 })));
    act(() => source.emit("run.failed", 7, { error_code: "AI_PROVIDER_BAD_RESPONSE" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Các kết quả đã hoàn tất được giữ lại");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.queryByText(/AI Task 2 Overall:/)).not.toBeInTheDocument();
    cleanup();
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [failed] });
    panel();
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(createAIWritingRun).toHaveBeenCalledTimes(1);
  });
});
