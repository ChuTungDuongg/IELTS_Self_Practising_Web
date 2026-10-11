/** One native recorder per physical container. No encoding or domain timers here. */
export function supportedMime(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((mime) => MediaRecorder.isTypeSupported(mime)) ?? null;
}
export class SpeakingRecorder {
  mimeType = "";
  onChunk: (chunk: Blob) => void = () => undefined;
  onLevel: (level: number) => void = () => undefined;
  onError: () => void = () => undefined;
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private recorder: MediaRecorder | null = null;
  private frame: number | null = null;
  private stopping: Promise<void> | null = null;
  get recording() { return this.recorder?.state === "recording"; }
  async prepare(deviceId?: string) {
    this.close();
    const mime = supportedMime();
    if (!mime || !navigator.mediaDevices?.getUserMedia || typeof AudioContext === "undefined") throw new Error("MICROPHONE_UNSUPPORTED");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true });
      this.mimeType = mime;
      this.context = new AudioContext(); await this.context.resume();
      const analyser = this.context.createAnalyser(); analyser.fftSize = 256;
      this.context.createMediaStreamSource(this.stream).connect(analyser);
      const values = new Uint8Array(analyser.fftSize);
      const sample = () => {
        analyser.getByteTimeDomainData(values);
        const rms = Math.sqrt(values.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / values.length);
        this.onLevel(Math.min(1, rms * 4));
        this.frame = requestAnimationFrame(sample);
      };
      sample();
    } catch (error) { this.close(); throw error; }
  }
  start() {
    if (this.recording) return;
    if (!this.stream || this.stream.getAudioTracks().some((track) => track.readyState !== "live")) throw new Error("MICROPHONE_REQUIRED");
    this.recorder = new MediaRecorder(this.stream, { mimeType: this.mimeType });
    this.stopping = null;
    this.recorder.addEventListener("dataavailable", (event) => { const chunk = (event as BlobEvent).data; if (chunk.size) this.onChunk(chunk); });
    this.recorder.addEventListener("error", () => this.onError());
    this.recorder.start(3000);
  }
  stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    const recorder = this.recorder;
    if (!recorder || recorder.state === "inactive") return Promise.resolve();
    this.stopping = new Promise<void>((resolve, reject) => {
      recorder.addEventListener("stop", () => resolve(), { once: true });
      recorder.addEventListener("error", () => reject(new Error("RECORDING_FAILED")), { once: true });
      recorder.stop();
    });
    return this.stopping;
  }
  close() {
    if (this.recording) this.recorder?.stop();
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.stream?.getTracks().forEach((track) => track.stop()); this.stream = null;
    void this.context?.close(); this.context = null;
  }
}
