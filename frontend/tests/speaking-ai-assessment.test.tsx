import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SpeakingAIAssessment } from "@/features/speaking/speaking-ai-assessment";
import * as api from "@/lib/api/speaking-ai";
import { LocaleProvider } from "@/lib/i18n/locale-provider";

vi.mock("@/lib/api/speaking-ai", () => ({ latestSpeakingAIRun: vi.fn(), createSpeakingAIRun: vi.fn(), getSpeakingAIRun: vi.fn(), cancelSpeakingAIRun: vi.fn(), watchSpeakingAIRun: vi.fn(), activeSpeakingAI: (run: api.SpeakingAIRun | null) => run?.status === "PENDING" || run?.status === "RUNNING" }));
const criterion: api.SpeakingAIRun["criteria"]["fc"] = { status: "WAITING", score: null, feedback_status: "PENDING", feedback: null, strengths: [], improvements: [], error_code: null, evidence_summary: {} };
const base = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "fixture", created_at: "now", status: "RUNNING", stage: "QUALITY_CHECK", last_sequence: 1, advisory: true, raw_mean: null, overall_band: null, criteria: { fc: criterion, lr: criterion, gra: criterion, pr: criterion }, error_code: null, summary: { responses: [] } } as api.SpeakingAIRun;
const close = vi.fn();
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.latestSpeakingAIRun).mockResolvedValue(null); vi.mocked(api.getSpeakingAIRun).mockResolvedValue(base); vi.mocked(api.createSpeakingAIRun).mockResolvedValue({ run_id: base.run_id, cache_hit: false, existing_active: false }); vi.mocked(api.watchSpeakingAIRun).mockReturnValue(close); });
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });
it("grades without a pre-generated transcript, suppresses double click, and only explicitly Stop cancels", async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.createSpeakingAIRun>>) => void;
  vi.mocked(api.createSpeakingAIRun).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  vi.mocked(api.cancelSpeakingAIRun).mockResolvedValue({ ...base, status: "CANCELLED", stage: "CANCELLED", last_sequence: 3 });
  const view = render(<SpeakingAIAssessment attemptId={base.attempt_id} />); const grade = await screen.findByRole("button", { name: "Grade with AI" });
  await act(async () => undefined); fireEvent.click(grade); fireEvent.click(grade); expect(api.createSpeakingAIRun).toHaveBeenCalledOnce();
  await act(async () => finish({ run_id: base.run_id, cache_hit: false, existing_active: false }));
  expect(screen.getByRole("status")).toHaveTextContent("Checking audio");
  fireEvent.click(screen.getByRole("button", { name: "Stop grading" })); await act(async () => undefined);
  expect(api.cancelSpeakingAIRun).toHaveBeenCalledExactlyOnceWith(base.attempt_id, base.run_id); expect(screen.getByRole("status")).toHaveTextContent("Grading stopped");
  view.unmount(); expect(api.cancelSpeakingAIRun).toHaveBeenCalledOnce();
});
it("resumes existing grading on mount and unmount only closes the observer", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue({ ...base, stage: "TRANSCRIBING" });
  const view = render(<SpeakingAIAssessment attemptId={base.attempt_id} />);
  expect(await screen.findByText("Transcribing")).toBeInTheDocument(); expect(api.createSpeakingAIRun).not.toHaveBeenCalled();
  view.unmount(); expect(close).toHaveBeenCalledOnce(); expect(api.cancelSpeakingAIRun).not.toHaveBeenCalled();
});
it("announces transcript availability once per grading run after transcription succeeds", async () => {
  const onTranscriptAvailable = vi.fn(); vi.mocked(api.latestSpeakingAIRun).mockResolvedValue({ ...base, stage: "TRANSCRIBING" });
  render(<SpeakingAIAssessment attemptId={base.attempt_id} onTranscriptAvailable={onTranscriptAvailable} />); await screen.findByText("Transcribing"); expect(onTranscriptAvailable).not.toHaveBeenCalled();
  const callbacks = vi.mocked(api.watchSpeakingAIRun).mock.calls[0][2];
  await act(async () => callbacks.snapshot({ ...base, stage: "ANALYSING_AUDIO", last_sequence: 2 }));
  await act(async () => callbacks.snapshot({ ...base, stage: "BUILDING_EVIDENCE", last_sequence: 3 }));
  await act(async () => callbacks.snapshot({ ...base, status: "COMPLETED", stage: "COMPLETED", last_sequence: 4 })); expect(onTranscriptAvailable).toHaveBeenCalledOnce();
  const nextId = "33333333-3333-4333-8333-333333333333";
  vi.mocked(api.createSpeakingAIRun).mockResolvedValue({ run_id: nextId, cache_hit: false, existing_active: false }); vi.mocked(api.getSpeakingAIRun).mockResolvedValue({ ...base, run_id: nextId, stage: "SCORING" });
  fireEvent.click(screen.getByRole("button", { name: "Grade with AI" })); await act(async () => undefined); expect(onTranscriptAvailable).toHaveBeenCalledTimes(2);
});
it("reuses a cached grading result returned by Grade instead of starting a second job", async () => {
  vi.mocked(api.createSpeakingAIRun).mockResolvedValue({ run_id: base.run_id, cache_hit: true, existing_active: false });
  vi.mocked(api.getSpeakingAIRun).mockResolvedValue({ ...base, status: "COMPLETED", stage: "COMPLETED", last_sequence: 9 });
  render(<SpeakingAIAssessment attemptId={base.attempt_id} />); const button = await screen.findByRole("button", { name: "Grade with AI" }); await act(async () => undefined); fireEvent.click(button);
  expect(await screen.findByText("Assessment complete")).toBeInTheDocument(); expect(api.createSpeakingAIRun).toHaveBeenCalledOnce(); expect(api.watchSpeakingAIRun).not.toHaveBeenCalled();
});
it.each(["FAILED", "CANCELLED"] as const)("resumes an explicitly requeued %s run with the same logical identity", async (status) => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue({ ...base, status, stage: status, last_sequence: 4 });
  vi.mocked(api.createSpeakingAIRun).mockResolvedValue({ run_id: base.run_id, cache_hit: false, existing_active: false });
  vi.mocked(api.getSpeakingAIRun).mockResolvedValue({ ...base, status: "PENDING", stage: "PENDING", last_sequence: 5 });
  render(<SpeakingAIAssessment attemptId={base.attempt_id} />); await screen.findByText(status === "FAILED" ? "Assessment unavailable" : "Grading stopped");
  expect(api.watchSpeakingAIRun).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Grade with AI" }));
  expect(await screen.findByRole("button", { name: "Stop grading" })).toBeInTheDocument(); expect(screen.getByRole("status")).toHaveTextContent("Queued for grading");
  await waitFor(() => expect(api.watchSpeakingAIRun).toHaveBeenCalledExactlyOnceWith(base.attempt_id, base.run_id, expect.any(Object), 5));
});
it("does not regress durable scores or reopen terminal results with stale snapshots", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue(base); render(<SpeakingAIAssessment attemptId={base.attempt_id} />); await screen.findByText("Checking audio");
  const callbacks = vi.mocked(api.watchSpeakingAIRun).mock.calls[0][2];
  const scored: api.SpeakingAIRun = { ...base, last_sequence: 3, stage: "SCORING", criteria: { ...base.criteria, fc: { ...criterion, status: "SCORED", score: 6.5, evidence_summary: { response_count: 3, opaque_reasoning: "PRIVATE_MODEL_REASONING" } } } };
  await act(async () => { callbacks.snapshot(scored); callbacks.snapshot({ ...base, last_sequence: 2 }); });
  expect(within(screen.getByRole("region", { name: "Fluency and Coherence" })).getByText("6.5")).toBeInTheDocument(); expect(screen.getByRole("status")).toHaveTextContent("Scoring");
  expect(screen.getByText("Whole-performance evidence: 3 responses")).toBeInTheDocument(); expect(screen.queryByText("PRIVATE_MODEL_REASONING")).toBeNull();
  await act(async () => callbacks.snapshot({ ...scored, status: "COMPLETED", stage: "COMPLETED", last_sequence: 4 }));
  await act(async () => callbacks.snapshot({ ...base, last_sequence: 5 }));
  expect(screen.getByRole("status")).toHaveTextContent("Assessment complete"); expect(screen.queryByRole("button", { name: "Stop grading" })).toBeNull();
});
it("keeps progressive scores through feedback fallback and shows unavailable pronunciation without a fake band", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue(base); render(<SpeakingAIAssessment attemptId={base.attempt_id} />); await screen.findByText("Checking audio");
  const callbacks = vi.mocked(api.watchSpeakingAIRun).mock.calls[0][2];
  await act(async () => callbacks.snapshot({ ...base, stage: "GENERATING_FEEDBACK", last_sequence: 2, criteria: { ...base.criteria, fc: { ...criterion, status: "SCORED", score: 6.5, feedback_status: "FALLBACK" }, pr: { ...criterion, status: "UNAVAILABLE", error_code: "SPEAKING_AUDIO_UNASSESSABLE" } } }));
  const fc = screen.getByRole("region", { name: "Fluency and Coherence" }); expect(within(fc).getByText("6.5")).toBeInTheDocument(); expect(within(fc).getByText(/Score saved; detailed feedback is unavailable/)).toBeInTheDocument();
  const pr = screen.getByRole("region", { name: "Pronunciation" }); expect(within(pr).getByText(/Unable to assess/)).toBeInTheDocument(); expect(within(pr).queryByText("1.0")).toBeNull();
  expect(screen.getAllByRole("region").filter((r) => r.classList.contains("speaking-ai-criterion"))).toHaveLength(4);
});
it("shows server advisory overall, raw mean, feedback and selected understandable evidence", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue({ ...base, status: "COMPLETED", stage: "COMPLETED", raw_mean: 6.375, overall_band: 6.5, criteria: { ...base.criteria, fc: { ...criterion, status: "COMPLETED", score: 6.5, feedback_status: "READY", feedback: "Fictional feedback.", strengths: ["Clear progression"], improvements: ["Extend examples"] } }, summary: { responses: [{ response_id: base.attempt_id, part_number: 2, words_per_minute: 115, part2_sustained_seconds: 93, pronunciation_status: "AVAILABLE", mean_alignment_confidence: .87, pitch_range_hz: 70, limitations: [] }] } });
  render(<SpeakingAIAssessment attemptId={base.attempt_id} />);
  expect(await screen.findByRole("heading", { name: "Advisory Overall Speaking Band" })).toBeInTheDocument(); expect(screen.getByText(/6.375/)).toBeInTheDocument();
  expect(screen.getByText("Fictional feedback.")).toBeInTheDocument(); expect(screen.getByText("Clear progression")).toBeInTheDocument(); expect(screen.getByText("Extend examples")).toBeInTheDocument();
  expect(screen.getByText(/115 words\/minute/)).toBeInTheDocument(); expect(screen.getByText(/93 seconds/)).toBeInTheDocument(); expect(screen.getByText(/87%/)).toBeInTheDocument(); expect(screen.getByText(/70 Hz/)).toBeInTheDocument();
});
it("hides mutations in teacher read-only mode while showing attached results", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue(base); render(<SpeakingAIAssessment attemptId={base.attempt_id} canGrade={false} />);
  expect(await screen.findByText("Checking audio")).toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Grade with AI" })).toBeNull(); expect(screen.queryByRole("button", { name: "Stop grading" })).toBeNull();
});
it("maps private provider failures to localized safe messages", async () => {
  localStorage.setItem("ielts-locale", "vi"); vi.mocked(api.latestSpeakingAIRun).mockRejectedValue(new Error("PRIVATE_MODEL_SECRET"));
  render(<LocaleProvider><SpeakingAIAssessment attemptId={base.attempt_id} /></LocaleProvider>);
  expect(await screen.findByRole("alert")).not.toHaveTextContent("PRIVATE_MODEL_SECRET");
  expect(screen.getByRole("alert")).toHaveTextContent("Không thể tải hoặc chấm bài Nói");
});
it("keeps quality failure explicit while retaining any previously saved criterion score", async () => {
  vi.mocked(api.latestSpeakingAIRun).mockResolvedValue({ ...base, status: "FAILED", stage: "FAILED", error_code: "SPEAKING_AUDIO_UNASSESSABLE", criteria: { ...base.criteria, lr: { ...criterion, status: "SCORED", score: 0, feedback_status: "FALLBACK" }, pr: { ...criterion, status: "UNAVAILABLE" } } });
  render(<SpeakingAIAssessment attemptId={base.attempt_id} />); await screen.findByText("Assessment unavailable");
  expect(within(screen.getByRole("region", { name: "Lexical Resource" })).getByText("0.0")).toBeInTheDocument(); expect(screen.getAllByText(/Unable to assess from the available audio/)).toHaveLength(2);
  expect(screen.getByText("Available when all four criteria are assessed")).toBeInTheDocument();
});
it("ignores a grading request that resolves after unmount without cancelling it", async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.createSpeakingAIRun>>) => void; vi.mocked(api.createSpeakingAIRun).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const view = render(<SpeakingAIAssessment attemptId={base.attempt_id} />); const button = await screen.findByRole("button", { name: "Grade with AI" }); await act(async () => undefined); fireEvent.click(button); view.unmount();
  await act(async () => finish({ run_id: base.run_id, cache_hit: false, existing_active: false }));
  expect(api.cancelSpeakingAIRun).not.toHaveBeenCalled(); expect(api.watchSpeakingAIRun).not.toHaveBeenCalled();
});
it("disables progress motion when system reduced-motion is requested", async () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })); vi.mocked(api.latestSpeakingAIRun).mockResolvedValue(base);
  render(<SpeakingAIAssessment attemptId={base.attempt_id} />); await screen.findByText("Checking audio");
  expect(screen.getByRole("region", { name: "Speaking AI assessment" })).toHaveAttribute("data-reduced-motion", "true");
});
