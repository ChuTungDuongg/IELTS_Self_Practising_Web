import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SpeakingRunner } from "@/features/speaking/speaking-runner";
import * as api from "@/lib/api/speaking";
import type { SpeakingState } from "@/lib/api/speaking";
import type { ExamPayload } from "@/lib/api/exam";
import { ApiError } from "@/lib/api/client";

const fakeRecorder = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn().mockResolvedValue(undefined), close: vi.fn(), onChunk: undefined as ((blob: Blob) => void) | undefined, onLevel: undefined, mimeType: "audio/webm;codecs=opus", recording: false }));
vi.mock("@/features/speaking/speaking-preflight", () => ({ SpeakingPreflight: ({ onReady }: { onReady(value: unknown): void }) => <button onClick={() => onReady(fakeRecorder)}>Ready microphone</button> }));
vi.mock("@/lib/api/speaking", async original => ({ ...await original<typeof api>(), getSpeakingState: vi.fn(), beginSpeaking: vi.fn(), heartbeatSpeaking: vi.fn(), finishSpeaking: vi.fn(), retrySpeaking: vi.fn(), saveSpeakingNotes: vi.fn(), openSpeakingSegment: vi.fn(), closeSpeakingSegment: vi.fn(), uploadSpeakingChunk: vi.fn(), getSpeakingManifest: vi.fn(), interruptSpeaking: vi.fn(), resumeSpeaking: vi.fn(), fetchSpeakingAudio: vi.fn(), selectSpeakingPrompt: vi.fn(), finishSpeakingPractice: vi.fn() }));
export const state: SpeakingState = {
  attempt_id: "11111111-1111-4111-8111-111111111111", mode: "PRACTICE", phase: "QUESTION_ENTER",
  current_prompt: { id: "22222222-2222-4222-8222-222222222222", part_number: 1, part_title: null, instructions: null, order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Fictional current question", preparation_seconds: 0, response_seconds: 60, config_json: {} },
  response_id: "33333333-3333-4333-8333-333333333333", take_number: 1, phase_started_at: null, phase_deadline_at: null, remaining_ms: 60000, server_time: new Date().toISOString(), can_retry: true, can_replay: true, scratch_notes: "", interruption_generation: 0, interruption_count: 0, recovery_state: null, recovery_grace_used: false, last_resumed_at: null,
  recovery_grace_deadline_at: null, recovery_grace_seconds: 7, recovery_allowed: false, next_segment_index: 0,
};
const initial = { test_title: "Fictional Speaking", attempt: { attempt_id: state.attempt_id } } as ExamPayload;
beforeEach(() => { vi.clearAllMocks(); fakeRecorder.recording = false; fakeRecorder.start.mockImplementation(() => { fakeRecorder.recording = true; }); fakeRecorder.stop.mockImplementation(async () => { fakeRecorder.recording = false; }); vi.mocked(api.getSpeakingState).mockResolvedValue(state); vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, phase: "RECORDING" }); vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...state, phase: "RECORDING" }); vi.mocked(api.openSpeakingSegment).mockResolvedValue({ id: "segment", segment_index: 0, mime_type: "audio/webm;codecs=opus", closed_at: null, chunk_count: null, chunks: [], content_url: null }); vi.mocked(api.closeSpeakingSegment).mockResolvedValue({} as never); vi.mocked(api.uploadSpeakingChunk).mockResolvedValue({} as never); vi.mocked(api.getSpeakingManifest).mockResolvedValue({ response: {} as never, segments: [] }); });
async function ready() { render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone")); await screen.findByText("Recording"); await waitFor(() => expect(screen.getByText("Done / Next")).toBeEnabled()); }

const freePrompts = [0, 1, 2].map(index => ({ ...state.current_prompt!, id: `22222222-2222-4222-8222-${String(index + 1).padStart(12, "0")}`, order_index: index, prompt_text: `Fictional free question ${index + 1}` }));
function freeState(index: number | null = null, phase: SpeakingState["phase"] = "BROWSING", committed: number[] = []): SpeakingState {
  const answered = index !== null && committed.includes(index);
  return { ...state, phase, current_prompt: index === null ? null : freePrompts[index], response_id: index !== null && (answered || phase === "RECORDING") ? state.response_id : null, take_number: index !== null && (answered || phase === "RECORDING") ? 1 : null, practice_flow: "FREE", focused_part_number: 1, can_retry: answered || phase === "RECORDING", can_replay: answered || phase === "RECORDING", can_finish_practice: committed.length > 0 && ["BROWSING", "QUESTION_ENTER"].includes(phase), navigation: freePrompts.map((p, position) => ({ id: p.id, order_index: position, current: position === index, status: committed.includes(position) ? "COMMITTED" : "UNANSWERED" })) };
}
async function readyFree(snapshot = freeState()) {
  vi.mocked(api.getSpeakingState).mockResolvedValue(snapshot);
  vi.mocked(api.selectSpeakingPrompt).mockImplementation(async (_id, prompt) => freeState(freePrompts.findIndex(p => p.id === prompt), "QUESTION_ENTER"));
  vi.mocked(api.beginSpeaking).mockImplementation(async (_id, prompt) => freeState(freePrompts.findIndex(p => p.id === prompt), "RECORDING"));
  vi.mocked(api.heartbeatSpeaking).mockImplementation(async (_id, prompt) => freeState(freePrompts.findIndex(p => p.id === prompt), "RECORDING"));
  render(<SpeakingRunner initial={initial} />);
  fireEvent.click(await screen.findByText("Ready microphone"));
  await screen.findByRole("navigation", { name: "Practice questions" });
}
it("reconstructs Free picker from server state and selects arbitrary questions without recording", async () => {
  await readyFree(freeState(1, "BROWSING", [1]));
  expect(screen.getByRole("button", { name: "Question 2 · Answered" })).toHaveAttribute("aria-current", "step");
  expect(screen.getByRole("button", { name: "Finish Practice" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Listen" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Retry recording" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Question 3 · Not answered" }));
  await screen.findByText("Fictional free question 3");
  fireEvent.click(screen.getByRole("button", { name: "Question 1 · Not answered" }));
  await screen.findByText("Fictional free question 1");
  expect(api.selectSpeakingPrompt).toHaveBeenNthCalledWith(1, state.attempt_id, freePrompts[2].id);
  expect(api.selectSpeakingPrompt).toHaveBeenNthCalledWith(2, state.attempt_id, freePrompts[0].id);
  expect(api.beginSpeaking).not.toHaveBeenCalled(); expect(fakeRecorder.start).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Record" }));
  await screen.findByText("Recording");
  expect(api.beginSpeaking).toHaveBeenCalledExactlyOnceWith(state.attempt_id, freePrompts[0].id);
});
it("Free stop and switch waits for physical stop, chunk close and durable finish ACK", async () => {
  await readyFree(freeState(0, "QUESTION_ENTER"));
  fireEvent.click(screen.getByRole("button", { name: "Record" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Done / Next" })).toBeEnabled());
  let acknowledge!: (next: SpeakingState) => void;
  vi.mocked(api.finishSpeaking).mockImplementation(() => new Promise(resolve => { acknowledge = resolve; }));
  fireEvent.click(screen.getByRole("button", { name: "Question 3 · Not answered" }));
  expect(screen.getByRole("dialog", { name: "Switch question?" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continue recording" }));
  expect(api.finishSpeaking).not.toHaveBeenCalled(); expect(fakeRecorder.recording).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Question 3 · Not answered" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop & switch" }));
  await waitFor(() => expect(api.finishSpeaking).toHaveBeenCalled());
  expect(fakeRecorder.recording).toBe(false); expect(api.closeSpeakingSegment).toHaveBeenCalled();
  expect(api.selectSpeakingPrompt).not.toHaveBeenCalled(); expect(screen.getByText("Fictional free question 1")).toBeInTheDocument();
  await act(async () => acknowledge(freeState(0, "BROWSING", [0])));
  await screen.findByText("Fictional free question 3");
  expect(api.selectSpeakingPrompt).toHaveBeenCalledExactlyOnceWith(state.attempt_id, freePrompts[2].id);
  expect(api.beginSpeaking).toHaveBeenCalledTimes(1);
});
it("failed Free switch persistence retains current prompt and recoverable selection", async () => {
  await readyFree(freeState(0, "QUESTION_ENTER"));
  fireEvent.click(screen.getByRole("button", { name: "Record" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Done / Next" })).toBeEnabled());
  vi.mocked(api.finishSpeaking).mockRejectedValueOnce(new Error("fictional save failure"));
  fireEvent.click(screen.getByRole("button", { name: "Question 3 · Not answered" }));
  fireEvent.click(screen.getByRole("button", { name: "Stop & switch" }));
  await screen.findByRole("alert");
  expect(api.selectSpeakingPrompt).not.toHaveBeenCalled(); expect(screen.getByText("Fictional free question 1")).toBeInTheDocument();
});
it("Free does not auto-finish last question and uses explicit confirmed Finish Practice", async () => {
  await readyFree(freeState(2, "BROWSING", [2]));
  expect(api.finishSpeakingPractice).not.toHaveBeenCalled(); expect(api.beginSpeaking).not.toHaveBeenCalled();
  vi.mocked(api.finishSpeakingPractice).mockResolvedValue({ ...freeState(2, "COMPLETED", [2]), current_prompt: null });
  fireEvent.click(screen.getByRole("button", { name: "Finish Practice" }));
  expect(api.finishSpeakingPractice).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Finish Practice" }));
  expect(await screen.findByRole("link", { name: "Review recording" })).toBeInTheDocument();
  expect(api.finishSpeakingPractice).toHaveBeenCalledExactlyOnceWith(state.attempt_id);
});
it("Free cannot finish with zero saved responses and Guided has no question picker", async () => {
  const view = render(<SpeakingRunner initial={initial} />);
  await screen.findByText("Ready microphone");
  expect(screen.queryByRole("navigation", { name: "Practice questions" })).toBeNull();
  view.unmount();
  await readyFree();
  expect(screen.getByRole("button", { name: "Finish Practice" })).toBeDisabled();
  expect(api.beginSpeaking).not.toHaveBeenCalled();
});
it("Free revisits a committed question, listens, and retries only its server-backed take", async () => {
  await readyFree(freeState(1, "BROWSING", [1]));
  fireEvent.click(screen.getByRole("button", { name: "Listen" }));
  await waitFor(() => expect(api.getSpeakingManifest).toHaveBeenCalledWith(state.attempt_id, state.response_id));
  vi.mocked(api.retrySpeaking).mockResolvedValue({ ...freeState(1, "RECORDING", [1]), take_number: 2 });
  fireEvent.click(screen.getByRole("button", { name: "Retry recording" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm retry" }));
  await waitFor(() => expect(api.retrySpeaking).toHaveBeenCalledExactlyOnceWith(state.attempt_id, freePrompts[1].id, 1));
  await screen.findByText("Recording");
  expect(api.selectSpeakingPrompt).not.toHaveBeenCalled(); expect(api.finishSpeakingPractice).not.toHaveBeenCalled();
});
it("renders current prompt and server recording state without a quick theme action", async () => { await ready(); expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument(); expect(screen.getByRole("timer")).toHaveTextContent("01:00"); expect(screen.getByRole("button", { name: "Done / Next" })).toBeEnabled(); expect(screen.queryByRole("button", { name: /Use (dark|light) theme/ })).not.toBeInTheDocument(); });
it("keeps current question until final acknowledgement and on failure", async () => {
  await ready(); let reject!: (reason: Error) => void;
  vi.mocked(api.finishSpeaking).mockImplementation(() => new Promise((_, fail) => { reject = fail; }));
  fireEvent.click(screen.getByText("Done / Next")); await screen.findByText("Saving...");
  expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument(); reject(new Error("network"));
  expect(await screen.findByRole("alert")).toHaveTextContent("save"); expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument();
});
it("exam offers neither listen nor retry", async () => {
  vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, mode: "EXAM", can_retry: false, can_replay: false, phase: "RECORDING" });
  await ready(); expect(screen.queryByText("Listen")).toBeNull(); expect(screen.queryByText("Retry recording")).toBeNull();
});
it("practice retry requires confirmation and consumes server take", async () => {
  await ready(); vi.mocked(api.retrySpeaking).mockResolvedValue({ ...state, phase: "RECORDING", take_number: 2 });
  fireEvent.click(screen.getByText("Retry recording")); expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Confirm retry")); await waitFor(() => expect(api.retrySpeaking).toHaveBeenCalledWith(state.attempt_id, state.current_prompt!.id, 1));
});
it("Part 2 preparation restores private notes without putting them in finish", async () => {
  const prep = { ...state, phase: "PREPARING", scratch_notes: "SPEAKING_PRIVATE_NOTE_SHOULD_NEVER_BE_GRADED", current_prompt: { ...state.current_prompt!, part_number: 2, prompt_type: "LONG_TURN", config_json: { cue_points: ["Fictional cue"] } } } as SpeakingState;
  vi.mocked(api.beginSpeaking).mockResolvedValue(prep); render(<SpeakingRunner initial={initial} />);
  fireEvent.click(await screen.findByText("Ready microphone")); expect(await screen.findByLabelText("Private scratch notes")).toHaveValue(prep.scratch_notes);
  expect(screen.getByText("Fictional cue")).toBeInTheDocument(); expect(api.finishSpeaking).not.toHaveBeenCalled();
});
it("renders server Part 2 preparation then recording without client granting time", async () => {
  vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, phase: "PREPARING" });
  render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone"));
  expect(await screen.findByText("Preparation")).toBeInTheDocument();
  expect(await screen.findByText("Recording", {}, { timeout: 2200 })).toBeInTheDocument();
});
it("server timeout finalizes once and receives completion acknowledgement", async () => {
  vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, phase: "FINALIZING", remaining_ms: 0 });
  vi.mocked(api.finishSpeaking).mockResolvedValue({ ...state, phase: "COMPLETED", current_prompt: null });
  render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone"));
  expect(await screen.findByText("Speaking completed")).toBeInTheDocument();
  expect(api.finishSpeaking).toHaveBeenCalledExactlyOnceWith(state.attempt_id, state.current_prompt!.id, 1, "TIMEOUT");
});
it("waits for durable final chunk acknowledgement before finish", async () => {
  await ready(); await waitFor(() => expect(api.openSpeakingSegment).toHaveBeenCalled());
  let acknowledge!: () => void; vi.mocked(api.uploadSpeakingChunk).mockImplementation(() => new Promise((resolve) => { acknowledge = () => resolve({} as never); }));
  fakeRecorder.onChunk!(new Blob(["final bytes"]));
  fireEvent.click(screen.getByText("Done / Next")); await screen.findByText("Saving...");
  expect(api.finishSpeaking).not.toHaveBeenCalled(); acknowledge();
  vi.mocked(api.finishSpeaking).mockResolvedValue({ ...state, phase: "COMPLETED", current_prompt: null });
  expect(await screen.findByText("Speaking completed")).toBeInTheDocument();
});
it("reload restores 31 seconds, server grace, and new recorder segment", async () => {
  vi.useFakeTimers();
  try {
    const interrupted = { ...state, phase: "INTERRUPTED", remaining_ms: 31000, interruption_generation: 1, next_segment_index: 1, server_time: new Date().toISOString() } as SpeakingState;
    vi.mocked(api.getSpeakingState).mockResolvedValue({ ...state, phase: "RECORDING" });
    vi.mocked(api.interruptSpeaking).mockResolvedValue(interrupted);
    vi.mocked(api.resumeSpeaking).mockResolvedValue({ ...interrupted, phase: "RECOVERY_GRACE", recovery_grace_deadline_at: new Date(Date.now() + 7000).toISOString() });
    vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...interrupted, phase: "RECOVERY_GRACE", recovery_grace_deadline_at: new Date(Date.now() + 7000).toISOString() });
    render(<SpeakingRunner initial={initial} />); await act(async () => {});
    fireEvent.click(screen.getByText("Ready microphone")); await act(async () => {});
    expect(screen.getByRole("timer")).toHaveTextContent("00:31");
    expect(screen.getByText("Recording resumes in 7")).toBeInTheDocument(); expect(fakeRecorder.start).not.toHaveBeenCalled();
    for (const count of [6, 5, 4, 3, 2, 1]) {
      vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...interrupted, phase: "RECOVERY_GRACE", server_time: new Date(Date.now() + 1000).toISOString(), recovery_grace_deadline_at: new Date(new Date(interrupted.server_time).getTime() + 7000).toISOString() });
      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
      expect(screen.getByText(`Recording resumes in ${count}`)).toBeInTheDocument();
      expect(screen.getByRole("timer")).toHaveTextContent("00:31");
    }
    vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...interrupted, phase: "RECORDING", server_time: new Date(Date.now() + 1000).toISOString() });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(api.openSpeakingSegment).toHaveBeenCalledWith(state.attempt_id, state.current_prompt!.id, 1, 1, "audio/webm;codecs=opus");
  } finally { vi.useRealTimers(); }
});
it("honors reduced motion and focuses the active question", async () => {
  const preference = window.matchMedia;
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() });
  try { await ready(); expect(screen.getByRole("main")).toHaveAttribute("data-reduced-motion", "true"); expect(screen.getByRole("heading", { name: state.current_prompt!.prompt_text })).toHaveFocus(); }
  finally { window.matchMedia = preference; }
});
it("practice listens to accepted audio and stops the current recorder", async () => {
  await ready(); vi.mocked(api.getSpeakingManifest).mockResolvedValue({ response: {} as never, segments: [{ id: "s", segment_index: 0, mime_type: "audio/webm", closed_at: "now", chunk_count: 1, chunks: [{ id: "c", sequence: 0, sha256: "hash", byte_size: 3 }], content_url: "/speaking-attempts/a/segments/s/content" }] });
  vi.mocked(api.fetchSpeakingAudio).mockResolvedValue(new Blob(["audio"]));
  const create = URL.createObjectURL; URL.createObjectURL = vi.fn().mockReturnValue("blob:current-take");
  try { fireEvent.click(screen.getByText("Listen")); fireEvent.click(await screen.findByText("Load recording")); expect(await screen.findByLabelText("Recording segment 1")).toHaveAttribute("src", "blob:current-take"); expect(fakeRecorder.stop).toHaveBeenCalled(); }
  finally { URL.createObjectURL = create; }
});
it("failed chunks are retained for save retry without advance", async () => {
  await ready(); vi.mocked(api.uploadSpeakingChunk).mockRejectedValue(new Error("offline"));
  fakeRecorder.onChunk!(new Blob(["pending"])); await screen.findByRole("alert");
  fireEvent.click(screen.getByText("Done / Next")); await waitFor(() => expect(api.closeSpeakingSegment).not.toHaveBeenCalled());
  expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument();
  vi.mocked(api.uploadSpeakingChunk).mockResolvedValue({} as never); vi.mocked(api.finishSpeaking).mockResolvedValue({ ...state, phase: "COMPLETED", current_prompt: null });
  await waitFor(() => expect(screen.getByText("Try saving again")).toBeEnabled());
  fireEvent.click(screen.getByText("Try saving again")); expect(await screen.findByText("Speaking completed")).toBeInTheDocument();
});
it("unmount releases recorder without finalizing backend", async () => {
  const view = render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone")); await waitFor(() => expect(screen.getByText("Done / Next")).toBeEnabled());
  view.unmount(); expect(fakeRecorder.close).toHaveBeenCalledOnce(); expect(api.finishSpeaking).not.toHaveBeenCalled();
});
it("practice can supersede a failed pending upload after explicit confirmation", async () => {
  await ready(); vi.mocked(api.uploadSpeakingChunk).mockRejectedValue(new Error("invalid chunk")); fakeRecorder.onChunk!(new Blob(["unsaved"]));
  await screen.findByRole("alert"); vi.mocked(api.retrySpeaking).mockResolvedValue({ ...state, phase: "RECORDING", take_number: 2 });
  fireEvent.click(screen.getByText("Retry recording")); fireEvent.click(screen.getByText("Confirm retry"));
  await waitFor(() => expect(api.openSpeakingSegment).toHaveBeenLastCalledWith(state.attempt_id, state.current_prompt!.id, 2, 0, "audio/webm;codecs=opus"));
  expect(api.finishSpeaking).not.toHaveBeenCalled();
});
it("stops capture at the last server deadline during a heartbeat outage", async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, phase: "RECORDING", remaining_ms: 1000 });
    vi.mocked(api.heartbeatSpeaking).mockRejectedValue(new Error("offline")); vi.mocked(api.finishSpeaking).mockRejectedValue(new Error("offline"));
    render(<SpeakingRunner initial={initial} />); await act(async () => {}); fireEvent.click(screen.getByText("Ready microphone")); await act(async () => {});
    expect(fakeRecorder.start).toHaveBeenCalledOnce(); await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(fakeRecorder.stop).toHaveBeenCalled(); expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument();
  } finally { vi.useRealTimers(); }
});
it("saves accepted audio when reconnect is no longer eligible without starting a microphone", async () => {
  vi.mocked(api.getSpeakingState).mockResolvedValueOnce({ ...state, phase: "RECORDING" }).mockResolvedValue({ ...state, phase: "FINALIZING", remaining_ms: 0 });
  vi.mocked(api.interruptSpeaking).mockRejectedValue(new ApiError("SPEAKING_RECOVERY_NOT_AVAILABLE", "Recovery unavailable", 409));
  vi.mocked(api.getSpeakingManifest).mockResolvedValue({ response: {} as never, segments: [{ id: "old-segment", segment_index: 0, mime_type: "audio/webm", closed_at: null, chunk_count: null, chunks: [{ id: "chunk", sequence: 0, sha256: "hash", byte_size: 3 }], content_url: null }] });
  vi.mocked(api.finishSpeaking).mockResolvedValue({ ...state, phase: "COMPLETED", current_prompt: null });
  render(<SpeakingRunner initial={initial} />);
  expect(await screen.findByText("Speaking completed")).toBeInTheDocument();
  expect(api.closeSpeakingSegment).toHaveBeenCalledExactlyOnceWith(state.attempt_id, "old-segment", 1);
  expect(api.finishSpeaking).toHaveBeenCalledExactlyOnceWith(state.attempt_id, state.current_prompt!.id, 1, "TIMEOUT");
  expect(fakeRecorder.start).not.toHaveBeenCalled(); expect(api.openSpeakingSegment).not.toHaveBeenCalled();
});
it("can reload runtime state after the initial network request fails", async () => {
  vi.mocked(api.getSpeakingState).mockRejectedValueOnce(new Error("offline"));
  render(<SpeakingRunner initial={initial} />); await screen.findByRole("alert");
  fireEvent.click(screen.getByText("Try saving again"));
  expect(await screen.findByText("Ready microphone")).toBeInTheDocument();
  expect(api.getSpeakingState).toHaveBeenCalledTimes(2); expect(api.finishSpeaking).not.toHaveBeenCalled();
});
it("does not offer capture when recovery is rejected for inconsistent active state", async () => {
  vi.mocked(api.getSpeakingState).mockResolvedValue({ ...state, phase: "RECORDING" });
  vi.mocked(api.interruptSpeaking).mockRejectedValue(new ApiError("SPEAKING_RECOVERY_NOT_AVAILABLE", "Recovery unavailable", 409));
  render(<SpeakingRunner initial={initial} />); await screen.findByRole("alert");
  expect(screen.queryByText("Ready microphone")).toBeNull();
  expect(fakeRecorder.start).not.toHaveBeenCalled(); expect(api.finishSpeaking).not.toHaveBeenCalled();
});
it("retries the same physical segment after its create acknowledgement is lost", async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.openSpeakingSegment).mockRejectedValueOnce(new Error("lost acknowledgement"));
    vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...state, phase: "RECORDING", next_segment_index: 1 });
    render(<SpeakingRunner initial={initial} />); await act(async () => {}); fireEvent.click(screen.getByText("Ready microphone")); await act(async () => {});
    expect(screen.getByRole("alert")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(fakeRecorder.start).toHaveBeenCalledOnce();
    expect(vi.mocked(api.openSpeakingSegment).mock.calls.map((call) => call[3])).toEqual([0, 0]);
    expect(api.finishSpeaking).not.toHaveBeenCalled();
  } finally { vi.useRealTimers(); }
});
it("removes the committed prompt's controls after advancing and captures only the next response", async () => {
  await ready();
  const next = { ...state, phase: "QUESTION_ENTER", response_id: null, take_number: null, current_prompt: { ...state.current_prompt!, id: "44444444-4444-4444-8444-444444444444", prompt_text: "Fictional next question" }, can_retry: false, can_replay: false } as SpeakingState;
  vi.mocked(api.finishSpeaking).mockResolvedValue(next);
  vi.mocked(api.beginSpeaking).mockResolvedValue({ ...next, phase: "RECORDING", response_id: "55555555-5555-4555-8555-555555555555", take_number: 1, can_retry: true, can_replay: true });
  fireEvent.click(screen.getByText("Done / Next")); await screen.findByText("Fictional next question");
  await waitFor(() => expect(api.openSpeakingSegment).toHaveBeenLastCalledWith(state.attempt_id, next.current_prompt!.id, 1, 0, "audio/webm;codecs=opus"));
  expect(screen.queryByText(state.current_prompt!.prompt_text)).toBeNull();
  expect(api.finishSpeaking).toHaveBeenCalledExactlyOnceWith(state.attempt_id, state.current_prompt!.id, 1, "USER_DONE");
});
it("refreshes a lost begin acknowledgement without interrupting the prepared microphone", async () => {
  vi.mocked(api.beginSpeaking).mockRejectedValueOnce(new Error("lost acknowledgement"));
  vi.mocked(api.getSpeakingState).mockResolvedValueOnce(state).mockResolvedValue({ ...state, phase: "RECORDING" });
  render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone"));
  await screen.findByRole("alert"); fireEvent.click(screen.getByText("Try saving again"));
  await waitFor(() => expect(fakeRecorder.start).toHaveBeenCalledOnce());
  expect(api.interruptSpeaking).not.toHaveBeenCalled(); expect(api.finishSpeaking).not.toHaveBeenCalled();
});
