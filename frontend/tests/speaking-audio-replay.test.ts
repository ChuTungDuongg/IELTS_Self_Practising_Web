import { afterEach, expect, it, vi } from "vitest";
import { SpeakingReplayController } from "@/features/speaking/speaking-audio-replay";
const span = { response_id: "response", take_number: 1, segment_id: "segment", start_ms: 2000, end_ms: 3000, normalized_start_ms: 9000, normalized_end_ms: 10000 };
function audio(duration: number) {
  const element = document.createElement("audio"); let paused = true;
  Object.defineProperty(element, "duration", { value: duration });
  Object.defineProperty(element, "paused", { get: () => paused });
  element.play = vi.fn(async () => { paused = false; }); element.pause = vi.fn(() => { paused = true; });
  element.playbackRate = 1; return element;
}
afterEach(() => vi.useRealTimers());
it.each([{ duration: 4, wantEnd: 3.5 }, { duration: 3.2, wantEnd: 3.2 }, { duration: Infinity, wantEnd: 3 }])("seeks source-relative time with bounded context and stops at $wantEnd for duration $duration", async ({ duration, wantEnd }) => {
  const controller = new SpeakingReplayController(); const recording = audio(duration);
  await controller.replay(recording, span, controller.beginRequest());
  expect(recording.currentTime).toBe(1.5); expect(recording.paused).toBe(false);
  recording.currentTime = wantEnd; controller.update(recording); expect(recording.paused).toBe(true);
});
it("uses a playback-rate-aware stop timer and clears it on pause and disposal", async () => {
  vi.useFakeTimers(); const controller = new SpeakingReplayController(); const recording = audio(10); recording.playbackRate = 2;
  await controller.replay(recording, span, controller.beginRequest());
  recording.currentTime = 3.5; await vi.advanceTimersByTimeAsync(1000); expect(recording.paused).toBe(true); expect(vi.getTimerCount()).toBe(0);
  await controller.replay(recording, span, controller.beginRequest()); controller.pause(recording); expect(vi.getTimerCount()).toBe(0);
  controller.update(recording); expect(vi.getTimerCount()).toBe(1); controller.stop(); expect(recording.paused).toBe(true); expect(vi.getTimerCount()).toBe(0);
});
it("ignores superseded replay requests and stops when seeking beyond the bounded end", async () => {
  const controller = new SpeakingReplayController(); const recording = audio(8); const obsolete = controller.beginRequest(); const latest = controller.beginRequest();
  await controller.replay(recording, span, obsolete); expect(recording.paused).toBe(true);
  await controller.replay(recording, span, latest); recording.currentTime = 7; controller.update(recording); expect(recording.paused).toBe(true);
});
