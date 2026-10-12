import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SpeakingTranscriptSession, SpeakingTranscriptResponse } from "@/features/speaking/speaking-transcript-panel";
import * as api from "@/lib/api/speaking-transcript";
import type { TranscriptRun } from "@/lib/api/speaking-transcript";

vi.mock("@/lib/api/speaking-transcript", () => ({ latestTranscriptRun: vi.fn(), createTranscriptRun: vi.fn(), getTranscriptRun: vi.fn(), watchTranscriptRun: vi.fn(), activeTranscript: (run: TranscriptRun | null) => run?.status === "PENDING" || run?.status === "RUNNING" }));
const run: TranscriptRun = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "key", status: "PARTIAL", last_sequence: 4, created_at: "now", responses: [
  { response_id: "33333333-3333-4333-8333-333333333333", status: "READY", verbatim: "um, He go to school.", clean: "um, He go to school.", words: [], error_code: null, source_audio_fingerprint: "audio1" },
  { response_id: "44444444-4444-4444-8444-444444444444", status: "FAILED", verbatim: null, clean: null, words: [], error_code: "TRANSCRIPT_GENERATION_FAILED", source_audio_fingerprint: "audio2" },
] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.latestTranscriptRun).mockResolvedValue(null); vi.mocked(api.createTranscriptRun).mockResolvedValue({ run_id: run.run_id, cache_hit: false, existing_active: false }); vi.mocked(api.getTranscriptRun).mockResolvedValue(run); vi.mocked(api.watchTranscriptRun).mockReturnValue(vi.fn()); });
function view() { return render(<SpeakingTranscriptSession attemptId={run.attempt_id}><section aria-label="Question 1"><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></section><section aria-label="Question 2"><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></section></SpeakingTranscriptSession>); }
it("generates read-only per-question transcripts and preserves one successful response", async () => {
  view(); const generate = screen.getByRole("button", { name: "Generate Transcript" });
  await waitFor(() => expect(generate).toBeEnabled()); fireEvent.click(generate);
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 1" })).getByText("Ready")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 2" })).getByText("Failed")).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull(); expect(screen.queryByText("Full Transcript")).toBeNull(); expect(screen.queryByText("Grade with AI")).toBeNull();
  expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(run.attempt_id);
});
it("restores an active run on reload and disconnects only observation on unmount", async () => {
  const active = { ...run, status: "RUNNING", responses: run.responses.map((r) => ({ ...r, status: "PROCESSING" })) } as TranscriptRun;
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(active); const disconnect = vi.fn(); vi.mocked(api.watchTranscriptRun).mockReturnValue(disconnect);
  const mounted = view(); await waitFor(() => expect(api.watchTranscriptRun).toHaveBeenCalled());
  expect(screen.getByText("Generate Transcript")).toBeDisabled();
  const callbacks = vi.mocked(api.watchTranscriptRun).mock.calls[0][2]; await act(async () => callbacks.snapshot(run));
  expect(screen.getByText("um, He go to school.")).toBeInTheDocument(); mounted.unmount(); expect(disconnect).toHaveBeenCalled();
  expect(api.createTranscriptRun).not.toHaveBeenCalled();
});
it("shows safe localized configuration error without private exception text", async () => {
  vi.mocked(api.createTranscriptRun).mockRejectedValue(new Error("SECRET path /raw"));
  view(); const generate = screen.getByRole("button", { name: "Generate Transcript" });
  // The label exists during restoration; clicking is valid only after it finishes.
  await waitFor(() => expect(generate).toBeEnabled()); fireEvent.click(generate);
  expect(await screen.findByRole("alert")).toHaveTextContent("Transcript is unavailable"); expect(screen.queryByText(/SECRET/)).toBeNull();
  expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(run.attempt_id);
});
it("waits for the restored run before enabling another generation request", async () => {
  let resolve!: (run: TranscriptRun | null) => void;
  vi.mocked(api.latestTranscriptRun).mockImplementation(() => new Promise((done) => { resolve = done; }));
  view(); const generate = screen.getByText("Generate Transcript");
  expect(generate).toBeDisabled(); fireEvent.click(generate); expect(api.createTranscriptRun).not.toHaveBeenCalled();
  await act(async () => resolve(null)); expect(generate).toBeEnabled();
});
it("assignment read-only review shows transcripts without mutation controls", async () => {
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(run);
  render(<SpeakingTranscriptSession attemptId={run.attempt_id} canGenerate={false}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession>);
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument(); expect(screen.queryByText("Generate Transcript")).toBeNull(); expect(screen.queryByText("Retry Transcript")).toBeNull();
});
it("double click starts one job and completed remount restores it without generation", async () => {
  let resolve!: (value: Awaited<ReturnType<typeof api.createTranscriptRun>>) => void;
  vi.mocked(api.createTranscriptRun).mockImplementation(() => new Promise((done) => { resolve = done; }));
  const mounted = view(); const button = await screen.findByText("Generate Transcript");
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button); fireEvent.click(button);
  expect(api.createTranscriptRun).toHaveBeenCalledTimes(1);
  await act(async () => resolve({ run_id: run.run_id, cache_hit: false, existing_active: false }));
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument(); mounted.unmount();
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(run); view();
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument();
  expect(api.createTranscriptRun).toHaveBeenCalledTimes(1);
});
it("keeps long ready text beside processing and failed questions without editable controls", async () => {
  const states = ["READY", "PROCESSING", "FAILED", "READY"] as const;
  const responses = states.map((status, i) => ({ ...run.responses[0], response_id: String(i), status, verbatim: status === "READY" ? `Q${i + 1} ${"spoken words ".repeat(500)}` : null }));
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses });
  render(<SpeakingTranscriptSession attemptId={run.attempt_id}>{responses.map((r, i) => <section key={r.response_id} aria-label={`Question ${i + 1}`}><SpeakingTranscriptResponse responseId={r.response_id} /></section>)}</SpeakingTranscriptSession>);
  await screen.findByText(/^Q1 spoken/);
  expect(within(screen.getByRole("region", { name: "Question 2" })).getByText("Processing")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 3" })).getByText("Failed")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 4" })).getByText(/^Q4 spoken/)).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull();
});
it("refreshes grading-generated transcripts through latest GET without starting transcription", async () => {
  const session = (refreshKey: number) => <SpeakingTranscriptSession attemptId={run.attempt_id} refreshKey={refreshKey}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession>;
  const mounted = render(session(0)); await act(async () => undefined); expect(screen.queryByText("um, He go to school.")).toBeNull();
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(run); mounted.rerender(session(1));
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument(); expect(api.latestTranscriptRun).toHaveBeenCalledTimes(2); expect(api.createTranscriptRun).not.toHaveBeenCalled();
});
it("ignores older latest responses after refresh and ignores pending refresh after unmount", async () => {
  let first!: (value: TranscriptRun | null) => void; let last!: (value: TranscriptRun | null) => void;
  vi.mocked(api.latestTranscriptRun).mockImplementationOnce(() => new Promise((resolve) => { first = resolve; })).mockResolvedValueOnce(run).mockImplementationOnce(() => new Promise((resolve) => { last = resolve; }));
  const session = (refreshKey: number) => <SpeakingTranscriptSession attemptId={run.attempt_id} refreshKey={refreshKey}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession>;
  const mounted = render(session(0)); mounted.rerender(session(1)); expect(await screen.findByText("um, He go to school.")).toBeInTheDocument();
  await act(async () => first(null)); expect(screen.getByText("um, He go to school.")).toBeInTheDocument();
  mounted.rerender(session(2)); mounted.unmount(); await act(async () => last(run)); expect(api.createTranscriptRun).not.toHaveBeenCalled(); expect(api.watchTranscriptRun).not.toHaveBeenCalled();
});
