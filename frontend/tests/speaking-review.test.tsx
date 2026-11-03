import { saveAssignmentSpeakingScore } from "@/lib/api/classroom-results";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { act, cleanup, fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SpeakingReview } from "@/features/speaking/speaking-review";
import * as api from "@/lib/api/speaking";
import * as transcriptApi from "@/lib/api/speaking-transcript";
import * as aiApi from "@/lib/api/speaking-ai";
vi.mock("@/lib/api/speaking", async (original) => ({ ...await original<typeof import("@/lib/api/speaking")>(), fetchSpeakingAudio: vi.fn(), saveSpeakingFinalScore: vi.fn() }));
vi.mock("@/lib/api/speaking-transcript", () => ({ latestTranscriptRun: vi.fn(), createTranscriptRun: vi.fn(), activeTranscript: () => false }));
vi.mock("@/lib/api/speaking-ai", async (original) => ({ ...await original<typeof import("@/lib/api/speaking-ai")>(), latestSpeakingAIRun: vi.fn(), createSpeakingAIRun: vi.fn(), getSpeakingAIRun: vi.fn(), watchSpeakingAIRun: vi.fn(), activeSpeakingAI: (run: aiApi.SpeakingAIRun | null) => run?.status === "PENDING" || run?.status === "RUNNING" }));
vi.mock("@/lib/api/classroom-results", async (original) => ({ ...await original<typeof import("@/lib/api/classroom-results")>(), saveAssignmentSpeakingScore: vi.fn() }));
const data = { attempt_id: "a", test_title: "Fictional review", parts: [{ part_number: 1, responses: [{ prompt: { id: "p", prompt_text: "Fictional reviewed question", config_json: {}, part_number: 1 }, response: { id: "r", duration_ms: 31000, completion_reason: "USER_DONE", status: "COMPLETED" }, segments: [{ id: "s", content_url: "/speaking-attempts/a/segments/s/content", mime_type: "audio/webm", chunks: [{ byte_size: 10 }] }] }] }] } as unknown as api.SpeakingReviewData;
beforeEach(() => { vi.clearAllMocks(); vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue(null); vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(null); vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:private", revokeObjectURL: vi.fn() }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it("groups authored responses and plays authorized audio by prompt", async () => {
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"])); render(<SpeakingReview data={data} />);
  expect(screen.getByRole("heading", { name: "Fictional review" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Use (dark|light) theme/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  expect(await screen.findByLabelText("Recording segment 1")).toHaveAttribute("src", "blob:private");
  expect(screen.getByText("31 s")).toBeInTheDocument(); expect(screen.getByText("Generate Transcript")).toBeInTheDocument(); expect(screen.getByText("Grade with AI")).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Transcript" })).toBeInTheDocument();
  expect(transcriptApi.latestTranscriptRun).toHaveBeenCalledOnce(); expect(aiApi.latestSpeakingAIRun).toHaveBeenCalledOnce();
});
it("displays safe authorization error", async () => {
  vi.mocked(api.fetchSpeakingAudio).mockRejectedValue(new Error("secret internal path")); render(<SpeakingReview data={data} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Recording access"); expect(screen.queryByText("secret internal path")).toBeNull();
});
it("loads only the selected response's physical segments", async () => {
  const second = { ...data.parts[0].responses[0], response: { ...data.parts[0].responses[0].response, id: "r2" }, prompt: { ...data.parts[0].responses[0].prompt, id: "p2", prompt_text: "Fictional second question" }, segments: [{ ...data.parts[0].responses[0].segments[0], id: "s2", content_url: "/speaking-attempts/a/segments/s2/content" }] };
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["second"])); render(<SpeakingReview data={{ ...data, parts: [{ ...data.parts[0], responses: [...data.parts[0].responses, second] }] }} />);
  const summary = screen.getByText("Fictional second question"); fireEvent.click(summary);
  fireEvent.click(within(summary.parentElement!).getByText("Load recording"));
  expect(await screen.findByLabelText("Recording segment 1")).toBeInTheDocument();
  expect(api.fetchSpeakingAudio).toHaveBeenCalledExactlyOnceWith("/speaking-attempts/a/segments/s2/content");
});
it("does not retain a playback URL when download finishes after unmount", async () => {
  let finish!: (blob: Blob) => void; vi.mocked(api.fetchSpeakingAudio).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const create = vi.spyOn(URL, "createObjectURL"); const view = render(<SpeakingReview data={data} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording")); view.unmount();
  await act(async () => finish(new Blob(["private"]))); expect(create).not.toHaveBeenCalled();
});
it("keeps transcript and AI mutation controls hidden for read-only classroom review", async () => {
  render(<SpeakingReview data={{ ...data, can_generate_transcript: false }} />); await act(async () => undefined);
  expect(screen.queryByText("Generate Transcript")).toBeNull(); expect(screen.queryByText("Grade with AI")).toBeNull(); expect(screen.queryByText("Stop grading")).toBeNull();
});
it("shows external-processing notice before an assessment is submitted", async () => {
  render(<SpeakingReview data={{ ...data, processing_profile: "speaking_hybrid_v1", external_audio_processing: true } as api.SpeakingReviewData} />);
  expect(screen.getByText(/Microsoft Azure/)).toBeInTheDocument(); expect(aiApi.createSpeakingAIRun).not.toHaveBeenCalled(); await act(async () => undefined);
});
it("shows the external-processing notice once when both review and saved run declare it", async () => {
  render(<SpeakingReview data={{ ...data, external_audio_processing: true }} initialAIRun={{ ...completedRun, summary: { responses: [], external_audio_processing: true } }} />);
  expect(screen.getAllByText(/Microsoft Azure/)).toHaveLength(1); await act(async () => undefined);
});
it("shows transcripts internally generated by Grade without another Generate click or reload", async () => {
  const criterion: aiApi.SpeakingAIRun["criteria"]["fc"] = { status: "WAITING", score: null, feedback_status: "PENDING", feedback: null, strengths: [], improvements: [], evidence_summary: {}, error_code: null };
  const run: aiApi.SpeakingAIRun = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "fixture", created_at: "now", status: "RUNNING", stage: "TRANSCRIBING", last_sequence: 1, advisory: true, raw_mean: null, overall_band: null, criteria: { fc: criterion, lr: criterion, gra: criterion, pr: criterion }, summary: { responses: [] }, error_code: null };
  vi.mocked(aiApi.createSpeakingAIRun).mockResolvedValue({ run_id: run.run_id, cache_hit: false, existing_active: false }); vi.mocked(aiApi.getSpeakingAIRun).mockResolvedValue(run); vi.mocked(aiApi.watchSpeakingAIRun).mockReturnValue(vi.fn());
  render(<SpeakingReview data={data} />); await act(async () => undefined); fireEvent.click(screen.getByRole("button", { name: "Grade with AI" })); await screen.findByText("Transcribing");
  vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue({ run_id: run.run_id, attempt_id: run.attempt_id, cache_key: "fixture", created_at: "now", status: "COMPLETED", last_sequence: 2, responses: [{ response_id: "r", status: "READY", verbatim: "Fictional internally generated transcript", clean: "Fictional internally generated transcript", words: [], error_code: null, source_audio_fingerprint: "fixture-audio" }] });
  await waitFor(() => expect(aiApi.watchSpeakingAIRun).toHaveBeenCalledExactlyOnceWith(data.attempt_id, run.run_id, expect.any(Object), 1));
  await act(async () => vi.mocked(aiApi.watchSpeakingAIRun).mock.calls[0][2].snapshot({ ...run, stage: "ANALYSING_AUDIO", last_sequence: 2 }));
  expect(await screen.findByText("Fictional internally generated transcript")).toBeInTheDocument(); expect(transcriptApi.createTranscriptRun).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Generate Transcript" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Grade with AI" })).toBeInTheDocument();
});

const completeCriterion: aiApi.SpeakingAIRun["criteria"]["fc"] = { status: "COMPLETED", score: 6.5, feedback_status: "READY", feedback: "Fictional feedback", strengths: [], improvements: [], error_code: null, evidence_summary: {} };
const completedRun: aiApi.SpeakingAIRun = { run_id: "run", attempt_id: "a", cache_key: "fictional", created_at: "now", status: "COMPLETED", stage: "COMPLETED", last_sequence: 9, advisory: true, raw_mean: 6.5, overall_band: 6.5, criteria: { fc: completeCriterion, lr: completeCriterion, gra: completeCriterion, pr: completeCriterion }, summary: { responses: [] }, error_code: null };
it.each([false, true])("copies current completed Speaking AI without persisting, then explicitly saves with classroom scope %s", async (classroom) => {
  vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(completedRun);
  const graded = { ...data, grading: { context: classroom ? "CLASSROOM" as const : "PERSONAL" as const, can_edit_final: true, can_copy_ai_to_final: true, waiting_for_teacher: false }, final_score: { fc: 7, lr: 6.5, gra: 6.5, pr: 6.5, overall_band: 6.5 } };
  vi.mocked(api.saveSpeakingFinalScore).mockResolvedValue(graded); vi.mocked(saveAssignmentSpeakingScore).mockResolvedValue(graded);
  render(<SpeakingReview data={{ ...graded, final_score: null }} assignmentScope={classroom ? { classroomId: "class", assignmentId: "assignment" } : undefined} />);
  fireEvent.click(await screen.findByRole("button", { name: "Copy AI scores to form" }));
  for (const key of ["FC", "LR", "GRA", "PR"]) expect(screen.getByLabelText(`Final ${key}`)).toHaveValue("6.5");
  expect(screen.getByLabelText("Final FC feedback")).toHaveValue("Fictional feedback");
  expect(api.saveSpeakingFinalScore).not.toHaveBeenCalled(); expect(saveAssignmentSpeakingScore).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Final FC"), { target: { value: "7.0" } });
  fireEvent.click(screen.getByRole("button", { name: "Copy AI scores to form" }));
  expect(screen.getByLabelText("Final FC")).toHaveValue("6.5");
  expect(api.saveSpeakingFinalScore).not.toHaveBeenCalled(); expect(saveAssignmentSpeakingScore).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Final FC"), { target: { value: "7.0" } });
  fireEvent.click(screen.getByRole("button", { name: "Save final score" }));
  await screen.findByText("Final score saved");
  const input = expect.objectContaining({ fc: 7, lr: 6.5, gra: 6.5, pr: 6.5, fc_feedback: "Fictional feedback" });
  if (classroom) { expect(saveAssignmentSpeakingScore).toHaveBeenCalledWith("class", "assignment", "a", input); expect(api.saveSpeakingFinalScore).not.toHaveBeenCalled(); }
  else { expect(api.saveSpeakingFinalScore).toHaveBeenCalledWith("a", input); expect(saveAssignmentSpeakingScore).not.toHaveBeenCalled(); }
});
it.each(["en", "vi"] as const)("classroom student sees localized %s waiting and no final mutations", async (locale) => {
  localStorage.setItem("ielts-locale", locale); vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(completedRun);
  render(<LocaleProvider><SpeakingReview data={{ ...data, grading: { context: "CLASSROOM", can_edit_final: false, can_copy_ai_to_final: false, waiting_for_teacher: true } }} /></LocaleProvider>);
  await waitFor(() => expect(screen.getByText(locale === "en" ? "Waiting for teacher grading" : "Đang chờ giáo viên chấm")).toBeInTheDocument());
  expect(screen.queryByRole("combobox")).toBeNull(); expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.queryByRole("button", { name: /Copy AI|Chép điểm AI|Save final|Lưu điểm cuối/ })).toBeNull();
  expect(api.saveSpeakingFinalScore).not.toHaveBeenCalled(); localStorage.clear();
});
it.each(["FAILED", "CANCELLED", "RUNNING"] as const)("does not copy %s Speaking scores into a final form", async (status) => {
  vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue({ ...completedRun, status, stage: status === "RUNNING" ? "SCORING" : status });
  render(<SpeakingReview data={{ ...data, grading: { context: "PERSONAL", can_edit_final: true, can_copy_ai_to_final: true, waiting_for_teacher: false } }} />);
  await act(async () => undefined); expect(screen.queryByRole("button", { name: "Copy AI scores to form" })).toBeNull(); expect(api.saveSpeakingFinalScore).not.toHaveBeenCalled();
});

it("shows Part and Free review context with unanswered prompts and no fabricated media", async () => {
  const basePrompt = data.parts[0].responses[0].prompt;
  render(<SpeakingReview data={{ ...data, focused_unit: { kind: "SPEAKING_PART", id: "part", order_index: 0, label: "Part 1", title: null }, practice_flow: "FREE", parts: [{ ...data.parts[0], responses: [{ ...data.parts[0].responses[0], prompt: { ...basePrompt, order_index: 1 } }], unanswered_prompts: [{ ...basePrompt, id: "unanswered-1", order_index: 0, prompt_text: "Fictional unanswered one" }, { ...basePrompt, id: "unanswered-3", order_index: 2, prompt_text: "Fictional unanswered three" }] }] }} />);
  expect(screen.getByText("Speaking Part 1 · Free question practice")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Speaking AI assessment · Part 1 practice" })).toBeInTheDocument();
  expect(screen.getAllByText("Not answered")).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Load recording" })).toHaveLength(1);
  expect(screen.getByText("Fictional unanswered one").closest("article")?.querySelector("audio")).toBeNull();
  await act(async () => undefined);
});

const localSpan = { response_id: "r", take_number: 2, segment_id: "s", start_ms: 200, end_ms: 1900, normalized_start_ms: 7200, normalized_end_ms: 8900 };
const localComment = { text: "Fictional pause evidence", evidence_ids: ["e1"], audio_span: localSpan, scope: "LOCAL" as const };
const replayData = { ...data, parts: [{ ...data.parts[0], responses: [{ ...data.parts[0].responses[0], response: { ...data.parts[0].responses[0].response, active_take_number: 2 } }] }] };
function withComments(comments = [localComment]) {
  return { ...completedRun, criteria: { ...completedRun.criteria, fc: { ...completeCriterion, local_comments: comments } } };
}
it("replays a server-resolved segment with bounded context and stops at the segment end", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"]));
  const view = render(<SpeakingReview data={replayData} initialAIRun={withComments()} />);
  await screen.findByText(localComment.text); expect(play).not.toHaveBeenCalled(); expect(api.fetchSpeakingAudio).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Listen to this segment" }));
  const audio = await screen.findByLabelText<HTMLAudioElement>("Recording segment 1");
  Object.defineProperty(audio, "duration", { configurable: true, value: 2 });
  Object.defineProperty(audio, "readyState", { configurable: true, value: 1 });
  fireEvent.loadedMetadata(audio);
  expect(api.fetchSpeakingAudio).toHaveBeenCalledExactlyOnceWith("/speaking-attempts/a/segments/s/content");
  expect(audio.closest("details")).toHaveAttribute("open"); expect(audio.currentTime).toBe(0); expect(play).toHaveBeenCalledOnce();
  audio.currentTime = 2; fireEvent.timeUpdate(audio); expect(pause).toHaveBeenCalled();
  view.unmount();
});
it("pauses another response recording before replay and ignores a stale take or segment", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  const second = { ...replayData.parts[0].responses[0], response: { ...replayData.parts[0].responses[0].response, id: "r2" }, prompt: { ...replayData.parts[0].responses[0].prompt, id: "p2", prompt_text: "Other fictional question" }, segments: [{ ...replayData.parts[0].responses[0].segments[0], id: "s2", content_url: "/speaking-attempts/a/segments/s2/content" }] };
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"]));
  render(<SpeakingReview data={{ ...replayData, parts: [{ ...replayData.parts[0], responses: [...replayData.parts[0].responses, second] }] }} initialAIRun={withComments([localComment, { ...localComment, text: "Old take", audio_span: { ...localSpan, take_number: 1 } }, { ...localComment, text: "Wrong segment", audio_span: { ...localSpan, segment_id: "s2" } }])} />);
  await screen.findByText(localComment.text); expect(screen.getAllByRole("button", { name: "Listen to this segment" })).toHaveLength(1);
  fireEvent.click(screen.getByText("Other fictional question")); fireEvent.click(within(screen.getByText("Other fictional question").closest("details")!).getByRole("button", { name: "Load recording" }));
  const other = await screen.findByLabelText<HTMLAudioElement>("Recording segment 1"); fireEvent.play(other); pause.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "Listen to this segment" }));
  expect(pause).toHaveBeenCalled(); expect(pause.mock.instances).toContain(other);
});
it("does not autoplay ordinary loaded audio and keeps native playback exclusive", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  const segment = replayData.parts[0].responses[0].segments[0];
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"]));
  render(<SpeakingReview data={{ ...replayData, parts: [{ ...replayData.parts[0], responses: [{ ...replayData.parts[0].responses[0], segments: [segment, { ...segment, id: "s3", segment_index: 2, content_url: "/speaking-attempts/a/segments/s3/content" }] }] }] }} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  const first = await screen.findByLabelText<HTMLAudioElement>("Recording segment 1"); const second = screen.getByLabelText<HTMLAudioElement>("Recording segment 2");
  expect(play).not.toHaveBeenCalled(); fireEvent.play(first); pause.mockClear(); fireEvent.play(second); expect(pause.mock.instances).toContain(first);
});
it("keeps loaded native playback running through unrelated review renders", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["private"]));
  const view = render(<SpeakingReview data={replayData} />);
  fireEvent.click(screen.getByText("Fictional reviewed question")); fireEvent.click(screen.getByText("Load recording"));
  const audio = await screen.findByLabelText<HTMLAudioElement>("Recording segment 1"); fireEvent.play(audio); pause.mockClear();
  view.rerender(<SpeakingReview data={{ ...replayData, test_title: "Updated fictional title" }} />);
  expect(pause).not.toHaveBeenCalled();
});
it("ignores a superseded segment download without starting its playback", async () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(); vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  const finishes = new Map<string, (blob: Blob) => void>();
  vi.mocked(api.fetchSpeakingAudio).mockImplementation(path => new Promise(resolve => finishes.set(path, resolve)));
  const item = replayData.parts[0].responses[0]; const second = { ...item.segments[0], id: "s2", content_url: "/speaking-attempts/a/segments/s2/content" };
  render(<SpeakingReview data={{ ...replayData, parts: [{ ...replayData.parts[0], responses: [{ ...item, segments: [...item.segments, second] }] }] }} initialAIRun={withComments([localComment, { ...localComment, text: "Fictional second segment", audio_span: { ...localSpan, segment_id: "s2", start_ms: 2000, end_ms: 3000 } }])} />);
  const buttons = screen.getAllByRole("button", { name: "Listen to this segment" }); fireEvent.click(buttons[0]);
  await waitFor(() => expect(finishes.has("/speaking-attempts/a/segments/s/content")).toBe(true)); fireEvent.click(buttons[1]);
  await waitFor(() => expect(finishes.has(second.content_url!)).toBe(true));
  await act(async () => finishes.get("/speaking-attempts/a/segments/s/content")!(new Blob(["old"])));
  const stale = await screen.findByLabelText<HTMLAudioElement>("Recording segment 1"); Object.defineProperty(stale, "readyState", { value: 1 }); Object.defineProperty(stale, "duration", { value: 5 }); fireEvent.loadedMetadata(stale); expect(play).not.toHaveBeenCalled();
  await act(async () => finishes.get(second.content_url!)!(new Blob(["current"])));
  const current = await screen.findByLabelText<HTMLAudioElement>("Recording segment 2"); Object.defineProperty(current, "readyState", { value: 1 }); Object.defineProperty(current, "duration", { value: 5 }); fireEvent.loadedMetadata(current);
  expect(play.mock.instances).toEqual([current]); expect(current.currentTime).toBe(1.5);
});
