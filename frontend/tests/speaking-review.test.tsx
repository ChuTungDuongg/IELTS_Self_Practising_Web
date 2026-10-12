import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SpeakingReview } from "@/features/speaking/speaking-review";
import * as api from "@/lib/api/speaking";
import * as transcriptApi from "@/lib/api/speaking-transcript";
import * as aiApi from "@/lib/api/speaking-ai";
vi.mock("@/lib/api/speaking", () => ({ fetchSpeakingAudio: vi.fn() }));
vi.mock("@/lib/api/speaking-transcript", () => ({ latestTranscriptRun: vi.fn(), createTranscriptRun: vi.fn(), activeTranscript: () => false }));
vi.mock("@/lib/api/speaking-ai", () => ({ latestSpeakingAIRun: vi.fn(), createSpeakingAIRun: vi.fn(), getSpeakingAIRun: vi.fn(), watchSpeakingAIRun: vi.fn(), activeSpeakingAI: (run: aiApi.SpeakingAIRun | null) => run?.status === "PENDING" || run?.status === "RUNNING" }));
const data = { attempt_id: "a", test_title: "Fictional review", parts: [{ part_number: 1, responses: [{ prompt: { id: "p", prompt_text: "Fictional reviewed question", config_json: {}, part_number: 1 }, response: { id: "r", duration_ms: 31000, completion_reason: "USER_DONE", status: "COMPLETED" }, segments: [{ id: "s", content_url: "/speaking-attempts/a/segments/s/content", mime_type: "audio/webm", chunks: [{ byte_size: 10 }] }] }] }] } as unknown as api.SpeakingReviewData;
beforeEach(() => { vi.clearAllMocks(); vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue(null); vi.mocked(aiApi.latestSpeakingAIRun).mockResolvedValue(null); vi.stubGlobal("URL", { ...URL, createObjectURL: () => "blob:private", revokeObjectURL: vi.fn() }); });
afterEach(() => vi.unstubAllGlobals());
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
it("shows transcripts internally generated by Grade without another Generate click or reload", async () => {
  const criterion: aiApi.SpeakingAIRun["criteria"]["fc"] = { status: "WAITING", score: null, feedback_status: "PENDING", feedback: null, strengths: [], improvements: [], evidence_summary: {}, error_code: null };
  const run: aiApi.SpeakingAIRun = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "fixture", created_at: "now", status: "RUNNING", stage: "TRANSCRIBING", last_sequence: 1, advisory: true, raw_mean: null, overall_band: null, criteria: { fc: criterion, lr: criterion, gra: criterion, pr: criterion }, summary: { responses: [] }, error_code: null };
  vi.mocked(aiApi.createSpeakingAIRun).mockResolvedValue({ run_id: run.run_id, cache_hit: false, existing_active: false }); vi.mocked(aiApi.getSpeakingAIRun).mockResolvedValue(run); vi.mocked(aiApi.watchSpeakingAIRun).mockReturnValue(vi.fn());
  render(<SpeakingReview data={data} />); await act(async () => undefined); fireEvent.click(screen.getByRole("button", { name: "Grade with AI" })); await screen.findByText("Transcribing");
  vi.mocked(transcriptApi.latestTranscriptRun).mockResolvedValue({ run_id: run.run_id, attempt_id: run.attempt_id, cache_key: "fixture", created_at: "now", status: "COMPLETED", last_sequence: 2, responses: [{ response_id: "r", status: "READY", verbatim: "Fictional internally generated transcript", clean: "Fictional internally generated transcript", words: [], error_code: null, source_audio_fingerprint: "fixture-audio" }] });
  await act(async () => vi.mocked(aiApi.watchSpeakingAIRun).mock.calls[0][2].snapshot({ ...run, stage: "ANALYSING_AUDIO", last_sequence: 2 }));
  expect(await screen.findByText("Fictional internally generated transcript")).toBeInTheDocument(); expect(transcriptApi.createTranscriptRun).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Generate Transcript" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "Grade with AI" })).toBeInTheDocument();
});
