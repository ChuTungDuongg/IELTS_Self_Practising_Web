import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { ApiError } from "@/lib/api/client";
import { SpeakingTranscriptSession, SpeakingTranscriptResponse } from "@/features/speaking/speaking-transcript-panel";
import * as api from "@/lib/api/speaking-transcript";
import type { TranscriptRun } from "@/lib/api/speaking-transcript";

vi.mock("@/lib/api/speaking-transcript", () => ({ latestTranscriptRun: vi.fn(), createTranscriptRun: vi.fn(), getTranscriptRun: vi.fn(), watchTranscriptRun: vi.fn(), activeTranscript: (run: TranscriptRun | null) => run?.status === "PENDING" || run?.status === "RUNNING" }));
const run: TranscriptRun = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "key", status: "PARTIAL", last_sequence: 4, created_at: "now", responses: [
  { response_id: "33333333-3333-4333-8333-333333333333", status: "READY", verbatim: "um, He go to school.", clean: "um, He go to school.", words: [], error_code: null, source_audio_fingerprint: "audio1" },
  { response_id: "44444444-4444-4444-8444-444444444444", status: "FAILED", verbatim: null, clean: null, words: [], error_code: "TRANSCRIPT_GENERATION_FAILED", source_audio_fingerprint: "audio2" },
] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.latestTranscriptRun).mockResolvedValue(null); vi.mocked(api.createTranscriptRun).mockResolvedValue({ run_id: run.run_id, cache_hit: false, existing_active: false }); vi.mocked(api.getTranscriptRun).mockResolvedValue(run); vi.mocked(api.watchTranscriptRun).mockReturnValue(vi.fn()); });
afterEach(() => localStorage.clear());
function view() { return render(<SpeakingTranscriptSession attemptId={run.attempt_id}><section aria-label="Question 1"><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></section><section aria-label="Question 2"><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></section></SpeakingTranscriptSession>); }
it.each(["FAILED", "PARTIAL"] as const)("explains Speech quota/throttling for a %s response without claiming monthly exhaustion", async (status) => {
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [
    { ...run.responses[0], status, error_code: "SPEAKING_AZURE_QUOTA_EXCEEDED" },
  ] });
  view();
  expect(await screen.findByRole("alert")).toHaveTextContent(/quota.*throttled.*try again later/i);
  expect(screen.queryByText(/5 hours|monthly quota/i)).not.toBeInTheDocument();
  expect(api.createTranscriptRun).not.toHaveBeenCalled();
});
it("shows a safe billing policy message for a rejected generation request", async () => {
  vi.mocked(api.createTranscriptRun).mockRejectedValue(new ApiError("SPEAKING_AZURE_BILLING_NOT_AUTHORIZED", "private provider body", 409));
  view();
  const button = screen.getByRole("button", { name: "Generate Transcript" });
  await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(/billing.*authorized/i);
  expect(screen.queryByText(/private provider body/)).not.toBeInTheDocument();
});
it.each([
  ["NO_SPEECH", /No speech was detected/, /Không phát hiện lời nói/],
  ["TOO_SHORT", /Too little audible speech/, /Phần lời nói nghe rõ quá ngắn/],
  ["VERY_LOW_SIGNAL", /recording volume is too low/, /Âm lượng bản ghi quá nhỏ/],
  ["AUDIO_CORRUPT", /audio file could not be read/, /Không đọc được tệp âm thanh/],
  ["SEVERE_CLIPPING", /recording is heavily distorted/, /Bản ghi bị méo tiếng nghiêm trọng/],
  ["BACKGROUND_DOMINANT", /Background noise dominates/, /Tiếng ồn nền lấn át/],
  ["ASR_UNUSABLE", /could not be recognized reliably/, /Chưa thể nhận dạng lời nói/],
  ["SPEAKING_AUDIO_UNASSESSABLE", /recording is unavailable or could not be read/, /Bản ghi hiện không khả dụng/],
  ["SPEAKING_ANALYSIS_BILLING_UNKNOWN", /acknowledge the possible Azure usage or charges/, /hãy xác nhận khả năng phát sinh hạn mức hoặc chi phí Azure/],
  ["SPEAKING_ASR_UNAVAILABLE", /Speech recognition is temporarily unavailable/, /Dịch vụ nhận dạng lời nói tạm thời chưa khả dụng/],
  ["TRANSCRIPT_SOURCE_CHANGED", /recording changed during processing/, /Bản ghi đã thay đổi/],
  ["TRANSCRIPT_CONFIGURATION_CHANGED", /settings changed during this request/, /Cấu hình xử lý lời nói đã thay đổi/],
] as const)("explains a saved %s failure in both locales without discarding successful text", async (code, english, vietnamese) => {
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [run.responses[0], { ...run.responses[1], error_code: code }] });
  for (const [locale, message] of [["en", english], ["vi", vietnamese]] as const) {
    localStorage.setItem("ielts-locale", locale);
    const mounted = render(<LocaleProvider><SpeakingTranscriptSession attemptId={run.attempt_id}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></SpeakingTranscriptSession></LocaleProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByText("um, He go to school.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    mounted.unmount();
  }
  expect(api.createTranscriptRun).not.toHaveBeenCalled();
});
it("gives safe fallback guidance for an unknown saved error without rendering its contents", async () => {
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [{ ...run.responses[1], error_code: "PRIVATE_PROVIDER_BODY /storage/private-audio" }] });
  render(<SpeakingTranscriptSession attemptId={run.attempt_id}><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></SpeakingTranscriptSession>);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Transcript is unavailable.*contact the administrator/);
  expect(screen.queryByText(/PRIVATE_PROVIDER_BODY|private-audio/)).not.toBeInTheDocument();
});
it("does not authorize resending interrupted requests by default", async () => {
  const interrupted = { ...run, responses: [run.responses[0], { ...run.responses[1], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" }] };
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(interrupted);
  vi.mocked(api.getTranscriptRun).mockResolvedValue(interrupted);
  view();
  expect(await screen.findByRole("checkbox")).not.toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Retry Transcript" }));
  await waitFor(() => expect(api.getTranscriptRun).toHaveBeenCalled());
  expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(run.attempt_id);
});
it.each(["en", "vi"] as const)("explains a stale interrupted-request authorization in %s", async (locale) => {
  localStorage.setItem("ielts-locale", locale);
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [{ ...run.responses[1], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" }] });
  vi.mocked(api.createTranscriptRun).mockRejectedValue(new ApiError("SPEAKING_INTERRUPTED_RETRY_NOT_AVAILABLE", "PRIVATE_BACKEND_DETAIL", 409));
  render(<LocaleProvider><SpeakingTranscriptSession attemptId={run.attempt_id}><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></SpeakingTranscriptSession></LocaleProvider>);
  fireEvent.click(await screen.findByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: locale === "en" ? "Retry Transcript" : "Thử tạo bản chép lời lại" }));
  expect(await screen.findByText(locale === "en" ? /transcript state has changed.*Reload the page/ : /Trạng thái bản chép lời đã thay đổi.*Tải lại trang/)).toBeInTheDocument();
  expect(screen.queryByText(/PRIVATE_BACKEND_DETAIL/)).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});
it.each(["en", "vi"] as const)("requires explicit %s acknowledgement to resend only interrupted failed responses", async (locale) => {
  localStorage.setItem("ielts-locale", locale);
  const interrupted = { ...run, responses: [
    { ...run.responses[0], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" },
    { ...run.responses[1], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" },
    { ...run.responses[1], response_id: "55555555-5555-4555-8555-555555555555", error_code: "TOO_SHORT" },
  ] };
  vi.mocked(api.latestTranscriptRun).mockResolvedValue(interrupted);
  vi.mocked(api.getTranscriptRun).mockResolvedValue(interrupted);
  render(<LocaleProvider><SpeakingTranscriptSession attemptId={run.attempt_id}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession></LocaleProvider>);
  const acknowledgement = await screen.findByRole("checkbox", { name: locale === "en" ? /resend 1 interrupted.*Azure usage or charges/ : /gửi lại 1 bản ghi bị gián đoạn.*hạn mức hoặc chi phí Azure/ });
  expect(acknowledgement).not.toBeChecked();
  fireEvent.click(acknowledgement);
  expect(api.createTranscriptRun).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: locale === "en" ? "Retry Transcript" : "Thử tạo bản chép lời lại" }));
  await waitFor(() => expect(api.getTranscriptRun).toHaveBeenCalled());
  expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(run.attempt_id, { responseIds: [run.responses[1].response_id], runId: run.run_id, lastSequence: run.last_sequence });
  expect(screen.getByText("um, He go to school.")).toBeInTheDocument();
  expect(acknowledgement).not.toBeChecked();
});
it.each(["sequence", "run", "attempt"] as const)("expires interrupted-request acknowledgement when the %s changes", async (change) => {
  const interrupted = { ...run, responses: [{ ...run.responses[1], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" }] };
  vi.mocked(api.latestTranscriptRun).mockResolvedValueOnce(interrupted);
  const session = (attemptId: string, refreshKey: number) => <SpeakingTranscriptSession attemptId={attemptId} refreshKey={refreshKey}><SpeakingTranscriptResponse responseId={run.responses[1].response_id} /></SpeakingTranscriptSession>;
  const mounted = render(session(run.attempt_id, 0));
  fireEvent.click(await screen.findByRole("checkbox"));
  expect(screen.getByRole("checkbox")).toBeChecked();
  const next = { ...interrupted, last_sequence: change === "sequence" ? run.last_sequence + 1 : run.last_sequence, run_id: change === "run" ? "66666666-6666-4666-8666-666666666666" : run.run_id, attempt_id: change === "attempt" ? "77777777-7777-4777-8777-777777777777" : run.attempt_id };
  vi.mocked(api.latestTranscriptRun).mockResolvedValueOnce(next);
  mounted.rerender(session(next.attempt_id, 1));
  await waitFor(() => expect(screen.getByRole("checkbox")).not.toBeChecked());
  fireEvent.click(screen.getByRole("button", { name: "Retry Transcript" }));
  await waitFor(() => expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(next.attempt_id));
});
it("generates read-only per-question transcripts and preserves one successful response", async () => {
  view(); const generate = screen.getByRole("button", { name: "Generate Transcript" });
  await waitFor(() => expect(generate).toBeEnabled()); fireEvent.click(generate);
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 1" })).getByText("Ready")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Question 2" })).getByText("Failed")).toBeInTheDocument();
  expect(screen.queryByRole("textbox")).toBeNull(); expect(screen.queryByText("Full Transcript")).toBeNull(); expect(screen.queryByText("Grade with AI")).toBeNull();
  expect(api.createTranscriptRun).toHaveBeenCalledExactlyOnceWith(run.attempt_id);
});
it.each(["en", "vi"] as const)("keeps partial lexical text visible with a localized %s limitation", async locale => {
  localStorage.setItem("ielts-locale", locale);
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [{ ...run.responses[0], status: "PARTIAL" as TranscriptRun["responses"][number]["status"], verbatim: "Fictional partial lexical transcript", clean: null }] });
  render(<LocaleProvider><SpeakingTranscriptSession attemptId={run.attempt_id}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession></LocaleProvider>);
  expect(await screen.findByText("Fictional partial lexical transcript")).toBeInTheDocument();
  expect(screen.getByText(locale === "en" ? /Partial transcript; some speech could not be transcribed/ : /Bản chép lời chưa đầy đủ/)).toBeInTheDocument(); expect(screen.queryByRole("textbox")).toBeNull();
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
  vi.mocked(api.latestTranscriptRun).mockResolvedValue({ ...run, responses: [run.responses[0], { ...run.responses[1], error_code: "SPEAKING_ANALYSIS_BILLING_UNKNOWN" }] });
  render(<SpeakingTranscriptSession attemptId={run.attempt_id} canGenerate={false}><SpeakingTranscriptResponse responseId={run.responses[0].response_id} /></SpeakingTranscriptSession>);
  expect(await screen.findByText("um, He go to school.")).toBeInTheDocument(); expect(screen.queryByText("Generate Transcript")).toBeNull(); expect(screen.queryByText("Retry Transcript")).toBeNull(); expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
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
