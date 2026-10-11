import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SpeakingPreflight } from "@/features/speaking/speaking-preflight";
import { SpeakingRecorder, supportedMime } from "@/features/speaking/speaking-recorder";

class Recorder extends EventTarget {
  static isTypeSupported = (mime: string) => mime === "audio/webm;codecs=opus";
  state = "inactive";
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.dispatchEvent(new MessageEvent("dataavailable", { data: new Blob(["fictional audio"]) })); this.dispatchEvent(new Event("stop")); }
}
function media(signal = true) {
  vi.stubGlobal("MediaRecorder", Recorder);
  const stop = vi.fn();
  const stream = { getTracks: () => [{ stop }], getAudioTracks: () => [{ readyState: "live" }] };
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue(stream), enumerateDevices: vi.fn().mockResolvedValue([{ kind: "audioinput", deviceId: "mic", label: "Fictional mic" }]) } });
  vi.stubGlobal("AudioContext", class {
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 256, getByteTimeDomainData: (data: Uint8Array) => data.fill(signal ? 145 : 128) }; }
    resume() { return Promise.resolve(); }
    close() { return Promise.resolve(); }
  });
  return stop;
}
afterEach(() => vi.unstubAllGlobals());
it("reports unsupported capture", async () => {
  vi.stubGlobal("MediaRecorder", undefined);
  render(<SpeakingPreflight onReady={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Check microphone" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("not supported");
});
it("reports permission denial safely", async () => {
  media(); vi.mocked(navigator.mediaDevices.getUserMedia).mockRejectedValue(new DOMException("private error", "NotAllowedError"));
  render(<SpeakingPreflight onReady={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Check microphone" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Microphone permission");
  expect(screen.queryByText("private error")).toBeNull();
});
it("selects opus, checks level and permits ready start", async () => {
  media(); const ready = vi.fn(); render(<SpeakingPreflight onReady={ready} />);
  fireEvent.click(screen.getByRole("button", { name: "Check microphone" }));
  const start = await screen.findByRole("button", { name: "Start Speaking" });
  await waitFor(() => expect(start).toBeEnabled());
  expect(screen.getByText("audio/webm;codecs=opus")).toBeInTheDocument();
  expect(screen.getByRole("meter")).toHaveAttribute("aria-valuenow");
  fireEvent.click(start); expect(ready).toHaveBeenCalledOnce();
});
it("silent input is not ready", async () => {
  media(false); render(<SpeakingPreflight onReady={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Check microphone" }));
  expect(await screen.findByRole("button", { name: "Start Speaking" })).toBeDisabled();
});
it("recorder flushes its final chunk and releases stream", async () => {
  const release = media(); const chunks: Blob[] = [];
  expect(supportedMime()).toBe("audio/webm;codecs=opus");
  const recorder = new SpeakingRecorder(); await recorder.prepare();
  recorder.onChunk = (chunk) => { chunks.push(chunk); };
  recorder.start(); await recorder.stop();
  expect(chunks[0].size).toBeGreaterThan(0); recorder.close(); expect(release).toHaveBeenCalled();
});
it("cancels a microphone request that resolves after unmount cleanup", async () => {
  media(); const release = vi.fn(); let permission!: (stream: MediaStream) => void;
  vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(() => new Promise((resolve) => { permission = resolve; }));
  const recorder = new SpeakingRecorder(); const pending = recorder.prepare(); recorder.close();
  permission({ getTracks: () => [{ stop: release }] } as unknown as MediaStream);
  try { await expect(pending).rejects.toThrow("MICROPHONE_CANCELLED"); expect(release).toHaveBeenCalledOnce(); }
  finally { recorder.close(); }
});
