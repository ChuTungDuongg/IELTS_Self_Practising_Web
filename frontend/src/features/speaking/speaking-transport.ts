import { ApiError } from "@/lib/api/client";

/** Keeps failed blobs until ACK; sequence/payload are never changed on retry. */
export class SpeakingChunkTransport {
  private chunks: Array<{ blob: Blob; acknowledged: boolean }> = [];
  private running: Promise<void> | null = null;
  private closed: Promise<void> | null = null;
  private disposed = false;
  constructor(private upload: (sequence: number, blob: Blob) => Promise<unknown>, private seal: (count: number) => Promise<unknown>, private onError: () => void) {}
  enqueue(blob: Blob) {
    if (this.disposed) return;
    if (this.closed) { this.onError(); return; }
    this.chunks.push({ blob, acknowledged: false });
    void this.flush().catch(this.onError);
  }
  flush(): Promise<void> {
    if (this.running) return this.running;
    this.running = (async () => {
      for (let sequence = 0; sequence < this.chunks.length; sequence++) {
        const item = this.chunks[sequence]; if (item.acknowledged) continue;
        for (let attempt = 0; ; attempt++) {
          if (this.disposed) return;
          try { await this.upload(sequence, item.blob); item.acknowledged = true; break; }
          catch (error) { if (attempt === 2 || (error instanceof ApiError && error.status >= 400 && error.status < 500)) throw error; }
        }
      }
    })().finally(() => { this.running = null; });
    return this.running;
  }
  close(): Promise<void> {
    if (this.closed) return this.closed;
    this.closed = this.flush().then(() => this.seal(this.chunks.length)).then(() => undefined).catch((error) => { this.closed = null; throw error; });
    return this.closed;
  }
  dispose() { this.disposed = true; this.chunks = []; }
}
