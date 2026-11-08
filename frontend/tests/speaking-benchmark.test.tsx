import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Page from "@/app/admin/speaking-benchmark/page";
import { SpeakingBenchmarkDetail } from "@/features/speaking-benchmark/sample-detail";
import { AudioReviewPlayer, useSourcePlayback } from "@/features/speaking-benchmark/audio-review-player";
import { overlapWindows } from "@/features/speaking-benchmark/speaker-timeline";
import { DiarizationJobStatus } from "@/features/speaking-benchmark/job-status";
import { ApiError } from "@/lib/api/client";
import * as api from "@/lib/api/speaking-benchmark";
import * as gradingApi from "@/lib/api/speaking-benchmark-grading";
import { renderWithLocale } from "./locale-test-utils";
import { labAvailable, labDraft, labLabels, labReview, labSample, labSampleId } from "./speaking-benchmark-fixtures";

const auth = vi.hoisted(() => ({ role: "ADMIN" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/speaking-benchmark", useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { role: auth.role }, loading: false, sessionError: null }) }));
vi.mock("@/lib/api/speaking-benchmark", async original => ({ ...await original<typeof api>(), listSpeakingSamples: vi.fn(), speakingAvailability: vi.fn(), uploadSpeakingSample: vi.fn(), getSpeakingSample: vi.fn(), getSpeakingReview: vi.fn(), getSpeakingLabels: vi.fn(), getSpeakingJobs: vi.fn(), saveSpeakingReview: vi.fn(), approveSpeakingReview: vi.fn(), saveSpeakingLabels: vi.fn(), queueSpeakingDiarization: vi.fn(), suggestSpeakingWindows: vi.fn() }));
vi.mock("@/lib/api/speaking-benchmark-grading", async original => ({ ...await original<typeof gradingApi>(), gradingAvailability: vi.fn(), approvedReviews: vi.fn(), listRuns: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks(); auth.role = "ADMIN"; window.localStorage.clear();
  vi.mocked(gradingApi.gradingAvailability).mockResolvedValue({ can_queue: false, live_status: "LIVE_UNVERIFIED", execution: "local", providers: [] });
  vi.mocked(gradingApi.approvedReviews).mockResolvedValue([]);
  vi.mocked(gradingApi.listRuns).mockResolvedValue([]);
  vi.mocked(api.listSpeakingSamples).mockResolvedValue({ items: [structuredClone(labSample)], total: 1, offset: 0, limit: 25 });
  vi.mocked(api.speakingAvailability).mockResolvedValue(labAvailable);
  vi.mocked(api.getSpeakingSample).mockResolvedValue(structuredClone(labSample));
  vi.mocked(api.getSpeakingReview).mockResolvedValue(structuredClone(labReview));
  vi.mocked(api.getSpeakingLabels).mockResolvedValue(structuredClone(labLabels));
  vi.mocked(api.getSpeakingJobs).mockResolvedValue([]);
  vi.mocked(api.saveSpeakingReview).mockImplementation(async (_id, draft, revision) => ({ ...labReview, draft, revision: revision + 1, approval_errors: [] }));
  vi.mocked(api.saveSpeakingLabels).mockImplementation(async (_id, value) => ({ ...value, revision: value.revision + 1 }));
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(); vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
});

describe("private Speaking lab", () => {
  it("separates recording review from labels while preserving unsaved text across keyboard tab navigation", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    const reviewTab = await screen.findByRole("tab", { name: "Recording review" });
    const humanTab = screen.getByRole("tab", { name: "Human Ground Truth" });
    expect(reviewTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Overall")).not.toBeVisible();
    fireEvent.change(screen.getByLabelText("Actual examiner question / cue-card topic"), { target: { value: "Keep my reviewed question" } });
    fireEvent.keyDown(reviewTab, { key: "ArrowRight" });
    expect(humanTab).toHaveFocus();
    expect(humanTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Overall")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Overall"), { target: { value: "6.5" } });
    fireEvent.click(reviewTab);
    expect(screen.getByLabelText("Actual examiner question / cue-card topic")).toHaveValue("Keep my reviewed question");
    fireEvent.click(humanTab);
    expect(screen.getByLabelText("Overall")).toHaveValue("6.5");
    expect(api.saveSpeakingReview).not.toHaveBeenCalled();
    expect(api.saveSpeakingLabels).not.toHaveBeenCalled();
  });
  it("makes an approved review available for evaluation on the same detail page", async () => {
    vi.mocked(api.getSpeakingReview).mockResolvedValue({ ...labReview, approval_errors: [] });
    vi.mocked(api.approveSpeakingReview).mockResolvedValue({ ...labReview, revision: 2, approval_errors: [], approved_at: "2026-11-08T00:00:00Z" });
    vi.mocked(api.getSpeakingSample).mockResolvedValueOnce(structuredClone(labSample)).mockResolvedValue({ ...labSample, review_revision: 2 });
    vi.mocked(gradingApi.approvedReviews).mockResolvedValueOnce([]).mockResolvedValue([{ revision: 2, approved_at: "2026-11-08T00:00:00Z" }]);
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    await screen.findByText("Approve candidate-only segmentation before evaluation.");
    fireEvent.click(screen.getByRole("button", { name: "Approve candidate segmentation" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    fireEvent.click(screen.getByRole("tab", { name: "AI Evaluation" }));
    expect(await screen.findByRole("option", { name: /2 ·/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Approved review revision")).toHaveValue("");
  });
  it.each(["USER", "TEACHER"])("denies %s before loading recordings", role => {
    auth.role = role; renderWithLocale(<Page />);
    expect(screen.getByRole("heading", { name: "Forbidden" })).toBeInTheDocument();
    expect(api.listSpeakingSamples).not.toHaveBeenCalled();
  });

  it("lists persisted owner samples and uploads with explicit rights", async () => {
    vi.mocked(api.uploadSpeakingSample).mockResolvedValue(labSample);
    renderWithLocale(<Page />); await screen.findByRole("link", { name: "DEV-051" });
    fireEvent.change(screen.getByLabelText("Sample code"), { target: { value: "NEW-1" } });
    fireEvent.change(screen.getByLabelText("Source and permission note"), { target: { value: "Synthetic recording permission" } });
    const form = screen.getByRole("button", { name: "Upload recording" }).closest("form")!;
    fireEvent.change(screen.getByLabelText("Original recording"), { target: { files: [new File(["RIFFtest"], "fixture.wav", { type: "audio/wav" })] } });
    fireEvent.click(screen.getByLabelText(/I have permission/)); fireEvent.submit(form);
    await waitFor(() => expect(api.uploadSpeakingSample).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.uploadSpeakingSample).mock.calls[0][1].rights_confirmed).toBe(true);
  });

  it("shows upload failure and retains form values", async () => {
    vi.mocked(api.uploadSpeakingSample).mockRejectedValue(new ApiError("REPLAY_AUDIO_UNREADABLE", "bad", 422));
    renderWithLocale(<Page />); await screen.findByLabelText("Sample code");
    const form = screen.getByRole("button", { name: "Upload recording" }).closest("form")!;
    fireEvent.change(screen.getByLabelText("Sample code"), { target: { value: "BAD-1" } });
    fireEvent.change(screen.getByLabelText("Original recording"), { target: { files: [new File(["corrupt"], "fixture.mp3")] } });
    fireEvent.click(screen.getByLabelText(/I have permission/));
    fireEvent.submit(form);
    expect(await screen.findByRole("alert")).toHaveTextContent("REPLAY_AUDIO_UNREADABLE");
    expect(screen.getByLabelText("Sample code")).toHaveValue("BAD-1");
  });

  it("selects candidate, edits windows and saves a new revision before approval", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    const role = await screen.findByLabelText("Role candidate");
    expect(screen.getByRole("button", { name: "Approve candidate segmentation" })).toBeDisabled();
    fireEvent.change(role, { target: { value: "candidate" } });
    fireEvent.click(screen.getByLabelText(/I listened and confirmed/));
    fireEvent.change(screen.getByLabelText("Start (seconds)"), { target: { value: "2.3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save review draft" }));
    await waitFor(() => expect(api.saveSpeakingReview).toHaveBeenCalledTimes(1));
    const saved = vi.mocked(api.saveSpeakingReview).mock.calls[0];
    expect(saved[2]).toBe(1); expect(saved[1].candidate_confirmed).toBe(true); expect(saved[1].segments[0].start_ms).toBe(2300);
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve candidate segmentation" })).toBeEnabled());
    expect(api.approveSpeakingReview).not.toHaveBeenCalled();
  });

  it("keeps draft text on a revision conflict", async () => {
    vi.mocked(api.saveSpeakingReview).mockRejectedValue(new ApiError("SPEAKING_BENCHMARK_REVISION_CONFLICT", "conflict", 409));
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    const prompt = await screen.findByLabelText("Actual examiner question / cue-card topic");
    fireEvent.change(prompt, { target: { value: "Unsaved actual human question" } }); fireEvent.click(screen.getByRole("button", { name: "Save review draft" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("newer revision"); expect(prompt).toHaveValue("Unsaved actual human question");
  });

  it("preserves unsaved review text when the locale changes", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    const prompt = await screen.findByLabelText("Actual examiner question / cue-card topic");
    fireEvent.change(prompt, { target: { value: "Keep this independently entered draft" } });
    const reads = vi.mocked(api.getSpeakingSample).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByLabelText("Câu hỏi giám khảo / chủ đề cue card thực tế")).toHaveValue("Keep this independently entered draft");
    expect(api.getSpeakingSample).toHaveBeenCalledTimes(reads);
  });

  it("keeps metadata save available while preventing conflicting review edits", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    await screen.findByLabelText("Role candidate");
    fireEvent.click(screen.getByText("Sample metadata"));
    fireEvent.change(screen.getByLabelText("Sample code"), { target: { value: "DEV-051-edited" } });
    expect(screen.getByLabelText("Part 2 starts at (seconds)")).toBeDisabled();
    expect(screen.getByLabelText("Start (seconds)")).toBeDisabled();
    expect(screen.getByLabelText("Actual examiner question / cue-card topic")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save metadata" })).toBeEnabled();
  });

  it("saves overall-only human labels without inventing criterion bands", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Human Ground Truth" }));
    fireEvent.change(await screen.findByLabelText("Overall"), { target: { value: "6.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save human labels" }));
    await waitFor(() => expect(api.saveSpeakingLabels).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.saveSpeakingLabels).mock.calls[0][1].bands).toEqual({ fc: null, lr: null, gra: null, pr: null, overall: 6.5 });
  });

  it.each([false, true])("keeps metadata protected through a label save (edited=%s)", async edited => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    await screen.findByLabelText("Overall");
    let resolveSample!: (value: api.SpeakingSample) => void;
    vi.mocked(api.getSpeakingSample).mockReturnValueOnce(new Promise(resolve => { resolveSample = resolve; }));
    fireEvent.click(screen.getByText("Sample metadata"));
    fireEvent.click(screen.getByRole("tab", { name: "Human Ground Truth" }));
    if (edited) fireEvent.change(screen.getByLabelText("Overall"), { target: { value: "6.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save human labels" }));
    await waitFor(() => expect(api.getSpeakingSample).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText("Sample code")).toBeDisabled();
    await act(async () => resolveSample({ ...labSample, revision: 3, label_revision: 1 }));
    await waitFor(() => expect(screen.getByLabelText("Sample code")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Sample code"), { target: { value: "KEEP-THIS-UNSAVED-CODE" } });
    expect(screen.getByLabelText("Sample code")).toHaveValue("KEEP-THIS-UNSAVED-CODE");
  });

  it("does not verify labels until human provenance and source exist", async () => {
    renderWithLocale(<SpeakingBenchmarkDetail sampleId={labSampleId} />);
    const verify = await screen.findByLabelText(/I independently verified/);
    expect(verify).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Label provenance"), { target: { value: "human_examiner" } });
    expect(verify).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Independent source / reference"), { target: { value: "Fictional human report" } });
    expect(verify).toBeEnabled();
  });

  it("plays, stops and seeks source windows using exactly one audio element", async () => {
    function Player() { const playback = useSourcePlayback(); return <><AudioReviewPlayer sampleId={labSampleId} durationMs={60000} playback={playback} /><button onClick={() => playback.play([{ start_ms: 2000, end_ms: 5000 }])}>Window</button></>; }
    const view = renderWithLocale(<Player />); const audio = view.container.querySelector("audio")!;
    expect(view.container.querySelectorAll("audio")).toHaveLength(1);
    fireEvent.click(screen.getByText("Window")); expect(audio.currentTime).toBe(2); expect(audio.play).toHaveBeenCalled();
    audio.currentTime = 5.1; fireEvent.timeUpdate(audio); expect(audio.pause).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Position (seconds)"), { target: { value: "22" } }); fireEvent.click(screen.getByRole("button", { name: "Seek" })); expect(audio.currentTime).toBe(22);
  });

  it("detects overlaps without joining distinct speaker evidence", () => {
    expect(overlapWindows([{ id: "a", speaker_id: "c", start_ms: 0, end_ms: 3000 }, { id: "b", speaker_id: "e", start_ms: 2000, end_ms: 4000 }])).toEqual([{ start_ms: 2000, end_ms: 3000 }]);
    expect(labDraft.candidate_confirmed).toBe(false);
  });

  it.each([['AbortError', false], ['NotAllowedError', true]] as const)("handles %s after stopping pending playback without hiding real failures", async (name, showError) => {
    let rejectPlay!: (reason: DOMException) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockReturnValueOnce(new Promise<void>((_resolve, reject) => { rejectPlay = reject; }));
    function Player() { const playback = useSourcePlayback(); return <><AudioReviewPlayer sampleId={labSampleId} durationMs={60000} playback={playback} /><button onClick={() => playback.play([{ start_ms: 2000, end_ms: 5000 }])}>Window</button></>; }
    renderWithLocale(<Player />);
    fireEvent.click(screen.getByRole("button", { name: /^Window$/ }));
    fireEvent.click(screen.getByRole("button", { name: "Stop window playback" }));
    await act(async () => rejectPlay(new DOMException("Synthetic playback interruption", name)));
    if (showError) expect(screen.getByRole("alert")).toBeInTheDocument();
    else expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("polls durable jobs and refreshes after completion", async () => {
    vi.useFakeTimers();
    try {
      const job: api.SpeakingJob = { id: labSampleId, status: "RUNNING", stage: "cpu_diarization", progress: 15, attempts: 1, error_code: null, created_at: "2026-11-07T00:00:00Z", started_at: null, finished_at: null };
      vi.mocked(api.getSpeakingJobs).mockResolvedValueOnce([job]).mockResolvedValueOnce([{ ...job, status: "COMPLETED", progress: 100 }]);
      const done = vi.fn();
      await act(async () => { renderWithLocale(<DiarizationJobStatus sampleId={labSampleId} generation={0} onFinished={done} />); });
      expect(screen.getByRole("progressbar")).toHaveAttribute("value", "15");
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(done).toHaveBeenCalledOnce();
    } finally { vi.useRealTimers(); }
  });

  it("refreshes once when the first job poll is already completed", async () => {
    const job: api.SpeakingJob = { id: labSampleId, status: "COMPLETED", stage: "completed", progress: 100, attempts: 1, error_code: null, created_at: "2026-11-07T00:00:00Z", started_at: null, finished_at: "2026-11-07T00:01:00Z" };
    vi.mocked(api.getSpeakingJobs).mockResolvedValue([job]);
    const done = vi.fn();
    renderWithLocale(<DiarizationJobStatus sampleId={labSampleId} generation={0} onFinished={done} />);
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    await waitFor(() => expect(api.getSpeakingJobs).toHaveBeenCalledTimes(2));
    expect(done).toHaveBeenCalledOnce();
  });

  it("rejects fabricated bands and AI label provenance in the typed contract", () => {
    expect(api.speakingLabelsSchema.safeParse({ ...labLabels, bands: { ...labLabels.bands, fc: 6.2 } }).success).toBe(false);
    expect(api.speakingLabelsSchema.safeParse({ ...labLabels, provenance: "ai_prediction", verified: true }).success).toBe(false);
  });
});
