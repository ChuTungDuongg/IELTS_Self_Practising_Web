import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingAIAssessment } from "@/features/writing/writing-ai-assessment";
import { Task1VisualStatus } from "@/features/writing/writing-ai-visual-details";
import { WritingReviewView } from "@/features/writing/writing-review";
import { CriterionAssessmentCard } from "@/features/writing/writing-ai-criterion-card";
import { humanizeSourceReferences, presentAIFeedback } from "@/features/writing/ai-feedback-presentation";
import { aiRunSchema, createAIWritingRun, getAIWritingRun, listAIWritingRuns, watchAIWritingRun, type AIWritingRun } from "@/lib/api/writing-ai";
import type { Task1Analysis } from "@/lib/api/task1-visual";
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
const visualAnalysis: Task1Analysis = {
  visual_family: "other", confidence: "LOW", derived_facts: [], warnings: ["VISUAL_LOW_CONFIDENCE"],
  reference: { visual_family: "other", confidence: "LOW", summary: "Thông tin ở P1S1 cần đối chiếu thêm.", uncertainty: ["Một số nhãn chưa rõ."], entities: [{ id: "e1", label: "Fictional parks" }], relationships: [], observations: ["Các khu vực được đánh dấu."] },
  claims: [{ claim_id: "c1", source_ids: ["P1S1"], quote: "  Fictional parks help.  ", claim: "Nhận định ở P1S1.", verdict: "INSUFFICIENT_EVIDENCE", explanation: "Chưa đủ dữ liệu tại P1S1.", evidence: [] }],
};
const taskOneResult = { ...result, task_number: 1 as const, task1_analysis: visualAnalysis,
  criteria: { ...result.criteria, ta: { ...criterion, feedback: "Mô tả tại P1S1." } } };
const pendingTaskOne: AIWritingRun = { ...pending, task_number: 1, prompt_version: "mts-task1-visual-v1" };
const completedTaskOne: AIWritingRun = { ...pendingTaskOne, status: "COMPLETED", result: taskOneResult, progress: taskOneResult.criteria, task1_analysis: visualAnalysis };

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

describe("AI feedback presentation", () => {
  it.each([
    ["P1S3", "đoạn 1, câu 3"],
    ["Xem P1S3 và P2S1.", "Xem đoạn 1, câu 3 và đoạn 2, câu 1."],
    ["(P1S4, P1S8, P2S12)", "(đoạn 1, câu 4; đoạn 1, câu 8; đoạn 2, câu 12)"],
    ["Tokyo (P1S8).", "Tokyo (đoạn 1, câu 8)."],
    ["Nhận xét không có mã nguồn.", "Nhận xét không có mã nguồn."],
    ["XP1S3 P1S3suffix _P1S3 P1S3_ AP1S3B tiếngP1S3 P1S3é", "XP1S3 P1S3suffix _P1S3 P1S3_ AP1S3B tiếngP1S3 P1S3é"],
    ["P0S3 P1S0 P01S3 p1s3 P1 S3 PS P S", "P0S3 P1S0 P01S3 p1s3 P1 S3 PS P S"],
    ["P1S3, P2S1suffix", "đoạn 1, câu 3, P2S1suffix"],
  ])("humanizes only standalone internal tokens in %s", (input, expected) => {
    expect(humanizeSourceReferences(input)).toBe(expected);
  });

  it("strips simple paired emphasis while preserving unmatched and complex markers", () => {
    expect(presentAIFeedback("**Rõ ràng** tại **P1S3**.")).toBe("Rõ ràng tại đoạn 1, câu 3.");
    expect(presentAIFeedback("Unpaired **marker; ***complex***; P/S.")).toBe("Unpaired **marker; ***complex***; P/S.");
  });

  it("humanizes every commentary section and leaves exact evidence quotes and IDs intact", () => {
    const quote = "  Fictional writers use **P1S3** literally.\nTheir words stay unchanged.  ";
    const grounded = {
      ...criterion,
      feedback: "**Ví dụ** ở P1S3 và P2S1.",
      strengths: ["Lập trường ở P1S4."],
      improvements: ["Phát triển (P1S8, P2S4)."],
      evidence: [{ source_id: "P4S99", quote, assessment: "Liên kết P1S3 với P2S4." }],
    };
    render(<CriterionAssessmentCard trait="ta" assessment={grounded} />);
    const card = screen.getByRole("article", { name: "AI Task Response" });
    expect(within(card).getByText("Ví dụ ở đoạn 1, câu 3 và đoạn 2, câu 1.")).toBeInTheDocument();
    expect(within(card).getByText("Lập trường ở đoạn 1, câu 4.")).toBeInTheDocument();
    expect(within(card).getByText("Phát triển (đoạn 1, câu 8; đoạn 2, câu 4).")).toBeInTheDocument();
    expect(within(card).getByText("Liên kết đoạn 1, câu 3 với đoạn 2, câu 4.")).toBeInTheDocument();
    for (const commentary of card.querySelectorAll("section, blockquote p")) {
      expect(commentary.textContent).not.toMatch(/P\d+S\d+/);
      expect(commentary.textContent).not.toContain("**");
    }
    expect(card.querySelector("q")?.textContent).toBe(quote);
    expect(card).not.toHaveTextContent("P4S99");
    expect(screen.getByText("Dẫn chứng từ bài viết (1)").closest("details")).not.toHaveAttribute("open");
    expect(grounded.feedback).toBe("**Ví dụ** ở P1S3 và P2S1.");
    expect(grounded.evidence[0]).toEqual({ source_id: "P4S99", quote, assessment: "Liên kết P1S3 với P2S4." });
  });
});

describe("Writing AI assessment", () => {
  it.each(["COMPLETED", "UNAVAILABLE", "PARSE_FAILED"] as const)("shows safe chart cross-check diagnostics and accepts old Task 1 history: %s", (status) => {
    const crossCheck = { specialist_used: status === "COMPLETED", specialist_model: "google/deplot", specialist_revision: "pinned", status, agreement_count: 6, disagreement_count: 0, unmatched_primary_count: 0, unmatched_specialist_count: 0, unknown_count: 0, warnings: [] };
    const analysis = { ...visualAnalysis, visual_family: "chart_table" as const, cross_check: crossCheck };
    const parsed = aiRunSchema.parse({ ...completedTaskOne, task1_analysis: analysis, result: { ...taskOneResult, task1_analysis: analysis } });
    render(<Task1VisualStatus analysis={parsed.task1_analysis!} />);
    expect(screen.getByText("Đối chiếu dữ liệu hình:")).toBeInTheDocument();
    expect(screen.getByText(status === "COMPLETED" ? "6 số liệu đã được xác nhận chéo." : "Không thể dùng bộ đối chiếu chuyên dụng; tiếp tục với phân tích hình chính.")).toBeInTheDocument();
    expect(screen.queryByText(/DePlot|google\/deplot/)).not.toBeInTheDocument();
    expect(aiRunSchema.parse(completedTaskOne).task1_analysis?.cross_check).toBeUndefined();
  });

  it("shows chart disagreement cautiously and suppresses specialist details on non-chart families", () => {
    const analysis = { ...visualAnalysis, visual_family: "chart_table" as const, cross_check: { specialist_used: true, specialist_model: "google/deplot", specialist_revision: "pinned", status: "COMPLETED" as const, agreement_count: 5, disagreement_count: 1, unmatched_primary_count: 0, unmatched_specialist_count: 0, unknown_count: 0, warnings: ["CHART_DATA_DISAGREEMENT" as const] } };
    const view = render(<Task1VisualStatus analysis={analysis} />);
    expect(screen.getByText(/Một số số liệu trong hình chưa được AI đọc thống nhất/)).toBeInTheDocument();
    view.rerender(<Task1VisualStatus analysis={{ ...analysis, visual_family: "process" }} />);
    expect(screen.queryByText("Đối chiếu dữ liệu hình:")).not.toBeInTheDocument();
  });
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
    expect(await screen.findByRole("region", { name: "AI Task 2 overall summary" })).toHaveTextContent("Band 6.5");
    expect(MockEventSource.instances[0].close).toHaveBeenCalled();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });

  it("restores cached completed results without starting inference", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    panel();
    expect(await screen.findByRole("region", { name: "AI Task 2 overall summary" })).toHaveTextContent("Band 6.5");
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(createAIWritingRun).not.toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it("shows an advisory overall Band and all four backend criterion scores", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
    panel();
    const summary = await screen.findByRole("region", { name: "AI Task 2 overall summary" });
    expect(within(summary).getByRole("heading", { name: "Điểm tổng hợp AI" })).toBeInTheDocument();
    expect(summary).toHaveTextContent("Band 6.5");
    expect(summary).toHaveTextContent("AI Task 2 · Ý kiến tham khảo");
    expect(summary).toHaveTextContent("Trung bình đều của 4 tiêu chí Task 2. Không phải band Writing chính thức.");
    for (const [label, name, score] of [
      ["TR", "Task Response", "6.5"], ["CC", "Coherence & Cohesion", "6.0"],
      ["LR", "Lexical Resource", "7.0"], ["GRA", "Grammatical Range & Accuracy", "6.0"],
    ]) {
      const stat = within(summary).getByText(label).closest("dt")!.parentElement!;
      expect(stat).toHaveTextContent(name);
      expect(within(stat).getByRole("definition")).toHaveTextContent(score);
    }
  });

  it("keeps the overall summary absent even after four progress cards until the complete result arrives", async () => {
    let resolveSnapshot!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { resolveSnapshot = resolve; })));
    panel(); await waitFor(() => expect(screen.getByRole("button")).toBeEnabled());
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const source = MockEventSource.instances[0];
    for (const [index, trait] of (["ta", "cc", "lr", "gra"] as const).entries()) {
      act(() => source.emit("criterion.completed", index + 1, { criterion: trait, result: result.criteria[trait] }));
    }
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
    act(() => source.emit("run.completed", 5));
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
    await act(async () => { resolveSnapshot(new Response(JSON.stringify(completed), { status: 200 })); });
    expect(await screen.findByRole("region", { name: "AI Task 2 overall summary" })).toHaveTextContent("Band 6.5");
  });

  it("humanizes old persisted feedback and copies it to every editable manual field without saving", async () => {
    const referencedResult = { ...result, criteria: {
      ta: { ...result.criteria.ta, feedback: "**Luận điểm** ở P1S13." },
      cc: { ...result.criteria.cc, feedback: "Liên kết (P1S3, P2S1)." },
      lr: { ...result.criteria.lr, feedback: "Từ vựng tại P2S4." },
      gra: { ...result.criteria.gra, feedback: "Cấu trúc tại P1S16." },
    } };
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [{ ...completed, prompt_version: "mts-task2-v1", result: referencedResult }] });
    render(<WritingReviewView data={review()} />);
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" }));
    const expected = {
      TA: "Luận điểm ở đoạn 1, câu 13.", CC: "Liên kết (đoạn 1, câu 3; đoạn 2, câu 1).",
      LR: "Từ vựng tại đoạn 2, câu 4.", GRA: "Cấu trúc tại đoạn 1, câu 16.",
    };
    for (const [trait, feedback] of Object.entries(expected)) {
      expect(screen.getByLabelText(`Task 2 ${trait} feedback`)).toHaveValue(feedback);
      expect(screen.getByLabelText(`Task 2 ${trait} feedback`)).toBeEnabled();
    }
    expect(screen.getByLabelText("AI Assessment").textContent).not.toMatch(/P\d+S\d+/);
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(referencedResult.criteria.ta.feedback).toBe("**Luận điểm** ở P1S13.");
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
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /6.5 · mts-task2-v2/ }));
    expect(screen.getByRole("region", { name: "AI Task 2 overall summary" })).toHaveTextContent("Band 6.5");
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
    expect(screen.getByRole("heading", { name: "Đánh giá AI · Task 1" })).toBeInTheDocument();
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
    await screen.findByRole("region", { name: "AI Task 2 overall summary" });
    expect(screen.queryByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" })).not.toBeInTheDocument();
  });

  it("uses the shared assessment controls for Task 1", async () => {
    const data = review(); data.tasks = data.tasks.filter((task) => task.task_number === 1);
    render(<WritingReviewView data={data} />);
    expect(await screen.findByRole("button", { name: "Chấm Task 1 với AI" })).toBeEnabled();
    expect(listAIWritingRuns).toHaveBeenCalledWith(attemptId, runId);
    expect(screen.queryByText("Task Response")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /6.5 · mts-task2-v1/ }));
    expect(screen.getByText(/Bản chấm cũ/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "AI Task 2 overall summary" })).toHaveTextContent("Band 6.5");
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
    expect(screen.queryByRole("region", { name: "AI Task 2 overall summary" })).not.toBeInTheDocument();
    cleanup();
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [failed] });
    panel();
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Tiến trình Lexical Resource")).toHaveAttribute("data-state", "FAILED");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(createAIWritingRun).toHaveBeenCalledTimes(1);
  });

  it("streams Task 1 grounding and claim verification, then immediate TA and the completed overall", async () => {
    vi.mocked(getAIWritingRun).mockResolvedValue(pendingTaskOne);
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy onCopy={vi.fn()} />);
    const grade = await screen.findByRole("button", { name: "Chấm Task 1 với AI" });
    await waitFor(() => expect(grade).toBeEnabled()); fireEvent.click(grade);
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const source = MockEventSource.instances[0];
    act(() => source.emit("visual_grounding.started", 1, { criterion: "ta", stage: "visual_grounding" }));
    expect(screen.getAllByText("Đang phân tích hình…")).toHaveLength(2);
    act(() => source.emit("visual_grounding.completed", 2, { task1_analysis: visualAnalysis }));
    expect(screen.getByText(/AI chưa đọc hình với độ tin cậy cao/)).toBeInTheDocument();
    act(() => source.emit("claim_verification.started", 3, { criterion: "ta", stage: "claim_verification" }));
    expect(screen.getAllByText("Đang đối chiếu nội dung bài viết với hình…")).toHaveLength(2);
    const beforeHeartbeat = screen.getByLabelText("Scoring Trace").textContent;
    act(() => source.emit("heartbeat", 4));
    expect(screen.getByLabelText("Scoring Trace").textContent).toBe(beforeHeartbeat);
    act(() => source.emit("claim_verification.completed", 5, { task1_analysis: visualAnalysis }));
    act(() => source.emit("criterion.completed", 6, { criterion: "ta", result: taskOneResult.criteria.ta }));
    const ta = screen.getByRole("article", { name: "AI Task Achievement" });
    expect(ta).toHaveTextContent("Mô tả tại đoạn 1, câu 1.");
    const visualDetails = within(ta).getByText("Đối chiếu với hình (1 nhận định)").closest("details")!;
    expect(visualDetails).not.toHaveAttribute("open");
    fireEvent.click(within(ta).getByText("Đối chiếu với hình (1 nhận định)"));
    expect(visualDetails.querySelector("q")?.textContent).toBe(visualAnalysis.claims[0].quote);
    expect(visualDetails).toHaveTextContent("Chưa đủ dữ liệu tại đoạn 1, câu 1.");
    expect(screen.getByLabelText("AI Assessment").textContent).not.toMatch(/P\d+S\d+/);
    expect(screen.queryByRole("region", { name: "AI Task 1 overall summary" })).not.toBeInTheDocument();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(completedTaskOne), { status: 200 })));
    act(() => source.emit("run.completed", 7));
    const overall = await screen.findByRole("region", { name: "AI Task 1 overall summary" });
    expect(overall).toHaveTextContent("Band 6.5");
    expect(overall).toHaveTextContent("Không phải band Writing chính thức.");
    for (const [label, score] of [["TA", "6.5"], ["CC", "6.0"], ["LR", "7.0"], ["GRA", "6.0"]]) {
      expect(within(overall).getByText(label).closest("dt")!.parentElement).toHaveTextContent(score);
    }
    expect(overall).toHaveTextContent("Task Achievement");
    expect(screen.queryByText("Task Response")).not.toBeInTheDocument();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });

  it("restores Task 1 cached confidence, typed results and exact claims without inference", async () => {
    const parsed = aiRunSchema.parse(completedTaskOne);
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [parsed] });
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy onCopy={vi.fn()} />);
    await screen.findByRole("region", { name: "AI Task 1 overall summary" });
    expect(screen.getByText(/Độ tin cậy khi đọc hình: Thấp/)).toBeInTheDocument();
    expect(screen.getByText(/AI chưa đọc hình với độ tin cậy cao/)).toBeInTheDocument();
    expect(parsed.task1_analysis?.claims[0].quote).toBe(visualAnalysis.claims[0].quote);
    expect(createAIWritingRun).not.toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
    expect(aiRunSchema.safeParse({ ...completedTaskOne, result: { ...taskOneResult, task1_analysis: { ...visualAnalysis, visual_family: "unknown" } } }).success).toBe(false);
    expect(aiRunSchema.parse(completed).result).toEqual(result);
  });

  it("copies humanized Task 1 suggestions into local manual state without saving or changing Task 2", async () => {
    vi.mocked(listAIWritingRuns).mockImplementation(async (_attempt, task) => ({ configured: true, items: task === runId ? [completedTaskOne] : [] }));
    render(<WritingReviewView data={review()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" }));
    for (const [trait, score] of [["TA", "6.5"], ["CC", "6.0"], ["LR", "7.0"], ["GRA", "6.0"]]) {
      expect(screen.getByLabelText(`Task 1 ${trait}`)).toHaveValue(score);
    }
    expect(screen.getByLabelText("Task 1 TA feedback")).toHaveValue("Mô tả tại đoạn 1, câu 1.");
    expect(screen.getByLabelText("Task 1 TA feedback")).toBeEnabled();
    expect(screen.getByLabelText("Task 2 TA")).toHaveValue("");
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(screen.getByText("Waiting for all 8 criterion scores")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Task 2/ }));
    expect(await screen.findByRole("button", { name: "Chấm Task 2 với AI" })).toBeInTheDocument();
    expect(screen.queryByText(/Độ tin cậy khi đọc hình/)).not.toBeInTheDocument();
  });

  it("retains failed TA while later language cards arrive and restores their persisted state", async () => {
    vi.mocked(getAIWritingRun).mockResolvedValue(pendingTaskOne);
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy onCopy={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button")).toBeEnabled()); fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    const source = MockEventSource.instances[0];
    const unusable = { ...visualAnalysis, confidence: "UNUSABLE" as const, reference: null, claims: [], warnings: ["VISUAL_GROUNDING_FAILED" as const] };
    act(() => source.emit("visual_grounding.failed", 1, { task1_analysis: unusable }));
    expect(screen.getByText(/CC, LR và GRA vẫn được chấm từ bài viết/)).toBeInTheDocument();
    const failure = { error_code: "AI_PROVIDER_BAD_RESPONSE", error_message: "Không thể hoàn tất tiêu chí này.", stage: "visual_grounding" as const };
    act(() => source.emit("criterion.failed", 2, { criterion: "ta", ...failure }));
    act(() => source.emit("criterion.started", 3, { criterion: "cc" }));
    expect(screen.getByLabelText("Tiến trình Task Achievement")).toHaveAttribute("data-state", "FAILED");
    expect(screen.getByLabelText("Tiến trình Coherence & Cohesion")).toHaveAttribute("data-state", "ACTIVE");
    for (const [index, trait] of (["cc", "lr", "gra"] as const).entries()) {
      act(() => source.emit("criterion.completed", index + 4, { criterion: trait, result: result.criteria[trait] }));
    }
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.queryByRole("region", { name: "AI Task 1 overall summary" })).not.toBeInTheDocument();
    const failed: AIWritingRun = { ...pendingTaskOne, status: "FAILED", task1_analysis: unusable, progress: { cc: result.criteria.cc, lr: result.criteria.lr, gra: result.criteria.gra }, failures: { ta: failure }, error_code: failure.error_code };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(failed), { status: 200 })));
    act(() => source.emit("run.failed", 7, { error_code: failure.error_code }));
    await screen.findByRole("alert"); cleanup();
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [failed] });
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy onCopy={vi.fn()} />);
    await screen.findByRole("alert");
    expect(screen.getAllByRole("article")).toHaveLength(3);
    expect(screen.getByLabelText("Tiến trình Task Achievement")).toHaveAttribute("data-state", "FAILED");
  });

  it("forces Task 1 regrade while retaining its completed history", async () => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completedTaskOne] });
    vi.mocked(getAIWritingRun).mockResolvedValue({ ...pendingTaskOne, id: taskId });
    vi.mocked(createAIWritingRun).mockResolvedValue({ run_id: taskId, cache_hit: false, existing_active: false });
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy onCopy={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Chấm lại với AI" }));
    await waitFor(() => expect(createAIWritingRun).toHaveBeenCalledWith(attemptId, taskId, true));
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(screen.getByText("Các bài chấm AI trước")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "AI Task 1 overall summary" })).not.toBeInTheDocument();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });
});
