import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WritingAIAssessment } from "@/features/writing/writing-ai-assessment";
import { WritingReviewView } from "@/features/writing/writing-review";
import { LocaleProvider, useLocale } from "@/lib/i18n/locale-provider";
import { aiWritingResultSchema, getAIPracticeFeedback, saveAIPracticeFeedback, listAIWritingRuns, createAIWritingRun, getAIWritingRun, cancelAIWritingRun, type AIWritingRun } from "@/lib/api/writing-ai";
import { saveWritingTaskScore, type WritingReviewPayload } from "@/lib/api/exam";
const auth = vi.hoisted(() => ({ role: "USER" }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { role: auth.role } }) }));
vi.mock("@/lib/api/writing-ai", async original => ({ ...await original<typeof import("@/lib/api/writing-ai")>(), getAIPracticeFeedback: vi.fn(), saveAIPracticeFeedback: vi.fn(), listAIWritingRuns: vi.fn(), createAIWritingRun: vi.fn(), getAIWritingRun: vi.fn(), cancelAIWritingRun: vi.fn() }));
vi.mock("@/lib/api/exam", async original => ({ ...await original<typeof import("@/lib/api/exam")>(), saveWritingTaskScore: vi.fn() }));
const attemptId = "11111111-1111-4111-8111-111111111111";
const taskId = "22222222-2222-4222-8222-222222222222";
const runId = "33333333-3333-4333-8333-333333333333";
const otherRun = "44444444-4444-4444-8444-444444444444";
const criterion = { score: 7, feedback: "Fictional saved feedback.", strengths: [], improvements: [], evidence: [] };
const result = { criteria: { ta: criterion, cc: criterion, lr: criterion, gra: criterion }, raw_mean: 7, overall_band: 7 };
const completed: AIWritingRun = { id: runId, attempt_id: attemptId, writing_task_id: taskId, status: "COMPLETED", provider: "fake", model: "fictional", prompt_version: "mts-task2-v8", result, progress: result.criteria, error_code: null, error_message: null, started_at: null, completed_at: "2026-10-11T00:00:00Z", created_at: "2026-10-11T00:00:00Z" };
const saved = { id: otherRun, attempt_id: attemptId, writing_task_id: taskId, source_run_id: runId, criteria: Object.fromEntries(Object.entries(result.criteria).map(([key, item]) => [key, { score: item.score, feedback: item.feedback }])), created_at: "2026-10-11T00:00:00Z", updated_at: "2026-10-11T01:00:00Z", relevance: null };
function review(scope: "FOCUSED_UNIT" | "FULL_MODULE", mock = false): WritingReviewPayload {
  return {
    review: { attempt: { attempt_id: attemptId, test_version_id: taskId, module: "WRITING", status: "SUBMITTED", scope, focused_unit: scope === "FOCUSED_UNIT" ? { kind: "WRITING_TASK", id: taskId, order_index: 1, label: "Task 2", title: null } : null, test_session_id: mock ? otherRun : null, finished_reason: "USER_SUBMIT", timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: saved.created_at, last_active_at: saved.created_at, finished_at: saved.created_at, paused_at: null, total_paused_seconds: 0, deadline_at: null, elapsed_seconds: 100, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: saved.created_at }, test_title: "Fictional practice", answers: [], writing_responses: [], highlights: [], flags: [] },
    tasks: [{ writing_task_id: taskId, task_number: 2, prompt: "Discuss fictional parks.", image_asset_id: null, image_asset: null, minimum_recommended_words: 250, recommended_duration_seconds: 2400, content: "Fictional parks help.", word_count: 3, score: null }],
    task1_overall: null, task2_overall: null, weighted_overall: null, band_score: null,
  };
}
function SwitchLocale() { const { setLocale } = useLocale(); return <button onClick={() => setLocale("vi")}>VI</button>; }
function panel() { return render(<LocaleProvider><SwitchLocale /><WritingAIAssessment attemptId={attemptId} taskId={taskId} hasEssay canCopy={false} canSavePersonalFeedback onCopy={vi.fn()} /></LocaleProvider>); }
beforeEach(() => {
  vi.resetAllMocks(); auth.role = "USER"; localStorage.clear();
  vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [completed] });
  vi.mocked(getAIPracticeFeedback).mockResolvedValue(null);
  vi.mocked(saveAIPracticeFeedback).mockResolvedValue(saved as Awaited<ReturnType<typeof saveAIPracticeFeedback>>);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe("focused personal AI feedback", () => {
  it("USER saves only a source run ID and sees four advisory scores separately", async () => {
    render(<WritingReviewView data={review("FOCUSED_UNIT")} />);
    fireEvent.click(await screen.findByRole("button", { name: "Save AI feedback to practice" }));
    await waitFor(() => expect(saveAIPracticeFeedback).toHaveBeenCalledExactlyOnceWith(attemptId, taskId, runId));
    const card = await screen.findByRole("region", { name: "Saved AI practice feedback" });
    expect(within(card).getByText("Advisory · Not an official score")).toBeInTheDocument();
    for (const name of ["Task Response", "Coherence & Cohesion", "Lexical Resource", "Grammatical Range & Accuracy"]) expect(within(card).getByText(name)).toBeInTheDocument();
    expect(within(card).getAllByText("7.0")).toHaveLength(4);
    expect(within(card).getByText(/Updated/)).toBeInTheDocument();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Chép gợi ý AI vào biểu mẫu" })).not.toBeInTheDocument();
  });
  it.each([["FULL_MODULE", false], ["FULL_MODULE", true], ["FOCUSED_UNIT", true]] as const)("USER %s mock=%s has neither save nor admin-copy action", async (scope, mock) => {
    render(<WritingReviewView data={review(scope, mock)} />);
    await screen.findByText("Chấm lại với AI");
    expect(screen.queryByText("Save AI feedback to practice")).not.toBeInTheDocument();
    expect(screen.queryByText("Chép gợi ý AI vào biểu mẫu")).not.toBeInTheDocument();
    expect(getAIPracticeFeedback).not.toHaveBeenCalled();
  });
  it("ADMIN keeps copying to official form and explicit manual save", async () => {
    auth.role = "ADMIN";
    render(<WritingReviewView data={review("FOCUSED_UNIT")} />);
    fireEvent.click(await screen.findByText("Chép gợi ý AI vào biểu mẫu"));
    expect(screen.getByRole("combobox", { name: "Task 2 TA" })).toHaveValue("7.0");
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
    expect(screen.queryByText("Save AI feedback to practice")).not.toBeInTheDocument();
    expect(getAIPracticeFeedback).not.toHaveBeenCalled();
  });
  it("loads the snapshot independently and never overwrites it on regrade", async () => {
    vi.mocked(getAIPracticeFeedback).mockResolvedValue(saved as Awaited<ReturnType<typeof getAIPracticeFeedback>>);
    vi.mocked(createAIWritingRun).mockResolvedValue({ run_id: otherRun, cache_hit: false, existing_active: false });
    vi.mocked(getAIWritingRun).mockResolvedValue({ ...completed, id: otherRun, result: { ...result, criteria: { ...result.criteria, ta: { ...criterion, score: 8 } } } });
    panel();
    const original = await screen.findByRole("region", { name: "Saved AI practice feedback" });
    fireEvent.click(await screen.findByText("Chấm lại với AI"));
    const update = await screen.findByRole("button", { name: "Update saved AI feedback" });
    expect(within(original).getAllByText("7.0")).toHaveLength(4);
    expect(saveAIPracticeFeedback).not.toHaveBeenCalled();
    vi.mocked(saveAIPracticeFeedback).mockResolvedValue({ ...saved, source_run_id: otherRun, criteria: { ...result.criteria, ta: { score: 8, feedback: criterion.feedback } } } as Awaited<ReturnType<typeof saveAIPracticeFeedback>>);
    fireEvent.click(update);
    await waitFor(() => expect(saveAIPracticeFeedback).toHaveBeenCalledExactlyOnceWith(attemptId, taskId, otherRun));
    expect(await within(original).findByText("8.0")).toBeInTheDocument();
  });
  it("new save and saved card chrome switch EN/VI without reloading or resetting the run", async () => {
    panel();
    await screen.findByRole("button", { name: "Save AI feedback to practice" });
    fireEvent.click(screen.getByText("VI"));
    fireEvent.click(screen.getByRole("button", { name: "Lưu nhận xét AI vào bài luyện" }));
    const card = await screen.findByRole("region", { name: "Nhận xét AI đã lưu cho bài luyện" });
    expect(within(card).getByText("Tham khảo · Không phải điểm chính thức")).toBeInTheDocument();
    expect(listAIWritingRuns).toHaveBeenCalledTimes(1);
    expect(cancelAIWritingRun).not.toHaveBeenCalled();
  });
  it("clearly explains unrelated TA/TR while preserving linguistic scores", async () => {
    const relevance = { verdict: "WHOLLY_UNRELATED" as const, confidence: "HIGH" as const, reason: "Nội dung hoàn toàn không liên quan đến đề.", evidence: [], short_circuit_applied: true };
    vi.mocked(getAIPracticeFeedback).mockResolvedValue({ ...saved, relevance, criteria: { ...result.criteria, ta: { score: 1, feedback: "Task Response Band 1." } } } as Awaited<ReturnType<typeof getAIPracticeFeedback>>);
    panel();
    const card = await screen.findByRole("region", { name: "Saved AI practice feedback" });
    expect(within(card).getByText(relevance.reason)).toBeInTheDocument();
    expect(within(card).getByText("1.0")).toBeInTheDocument();
    expect(within(card).getAllByText("7.0")).toHaveLength(3);
    expect(card.textContent).not.toMatch(/cheating|plagiarism|gian lận/i);
  });
  it.each(["PENDING", "RUNNING", "FAILED"] as const)("does not offer save for %s", async status => {
    vi.mocked(listAIWritingRuns).mockResolvedValue({ configured: true, items: [{ ...completed, status, result: null, progress: {} }] });
    if (status !== "FAILED") vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
    panel();
    await waitFor(() => expect(listAIWritingRuns).toHaveBeenCalled());
    expect(screen.queryByText("Save AI feedback to practice")).not.toBeInTheDocument();
  });
  it("failed save keeps the existing snapshot and supports retry", async () => {
    vi.mocked(getAIPracticeFeedback).mockResolvedValue({ ...saved, source_run_id: otherRun } as Awaited<ReturnType<typeof getAIPracticeFeedback>>);
    vi.mocked(saveAIPracticeFeedback).mockRejectedValueOnce(new Error("private failure"));
    panel();
    fireEvent.click(await screen.findByText("Update saved AI feedback"));
    expect(await screen.findByText("Could not save AI feedback. Please try again.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Saved AI practice feedback" })).toBeInTheDocument();
    expect(saveWritingTaskScore).not.toHaveBeenCalled();
  });
  it("historical result without relevance still validates", () => {
    expect(aiWritingResultSchema.parse(result).criteria.ta.score).toBe(7);
  });
  it("focused Task 1 keeps the Task Achievement label in personal feedback", async () => {
    vi.mocked(getAIPracticeFeedback).mockResolvedValue(saved as Awaited<ReturnType<typeof getAIPracticeFeedback>>);
    render(<WritingAIAssessment attemptId={attemptId} taskId={taskId} taskNumber={1} hasEssay canCopy={false} canSavePersonalFeedback onCopy={vi.fn()} />);
    const card = await screen.findByRole("region", { name: "Saved AI practice feedback" });
    expect(within(card).getByText("Task Achievement")).toBeInTheDocument();
    expect(within(card).queryByText("Task Response")).not.toBeInTheDocument();
  });
});
