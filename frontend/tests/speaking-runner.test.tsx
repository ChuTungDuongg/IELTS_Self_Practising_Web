import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SpeakingRunner } from "@/features/speaking/speaking-runner";
import * as api from "@/lib/api/speaking";
import type { SpeakingState } from "@/lib/api/speaking";
import type { ExamPayload } from "@/lib/api/exam";

const fakeRecorder = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn().mockResolvedValue(undefined), close: vi.fn(), onChunk: undefined, onLevel: undefined, mimeType: "audio/webm;codecs=opus", recording: false }));
vi.mock("@/features/speaking/speaking-preflight", () => ({ SpeakingPreflight: ({ onReady }: { onReady(value: unknown): void }) => <button onClick={() => onReady(fakeRecorder)}>Ready microphone</button> }));
vi.mock("@/lib/api/speaking", () => ({ getSpeakingState: vi.fn(), beginSpeaking: vi.fn(), heartbeatSpeaking: vi.fn(), finishSpeaking: vi.fn(), retrySpeaking: vi.fn(), saveSpeakingNotes: vi.fn() }));
export const state: SpeakingState = {
  attempt_id: "11111111-1111-4111-8111-111111111111", mode: "PRACTICE", phase: "QUESTION_ENTER",
  current_prompt: { id: "22222222-2222-4222-8222-222222222222", part_number: 1, part_title: null, instructions: null, order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Fictional current question", preparation_seconds: 0, response_seconds: 60, config_json: {} },
  response_id: "33333333-3333-4333-8333-333333333333", take_number: 1, phase_started_at: null, phase_deadline_at: null, remaining_ms: 60000, server_time: new Date().toISOString(), can_retry: true, can_replay: true, scratch_notes: "", interruption_generation: 0, interruption_count: 0, recovery_state: null, recovery_grace_used: false, last_resumed_at: null,
};
const initial = { test_title: "Fictional Speaking", attempt: { attempt_id: state.attempt_id } } as ExamPayload;
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.getSpeakingState).mockResolvedValue(state); vi.mocked(api.beginSpeaking).mockResolvedValue({ ...state, phase: "RECORDING" }); vi.mocked(api.heartbeatSpeaking).mockResolvedValue({ ...state, phase: "RECORDING" }); });
async function ready() { render(<SpeakingRunner initial={initial} />); fireEvent.click(await screen.findByText("Ready microphone")); await screen.findByText("Recording"); }
it("renders current prompt and server recording state", async () => { await ready(); expect(screen.getByText(state.current_prompt!.prompt_text)).toBeInTheDocument(); expect(screen.getByRole("timer")).toHaveTextContent("01:00"); expect(screen.getByRole("button", { name: "Done / Next" })).toBeEnabled(); });
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
