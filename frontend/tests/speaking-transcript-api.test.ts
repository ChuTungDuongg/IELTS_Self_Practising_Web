import { afterEach, expect, it, vi } from "vitest";
import { transcriptRunSchema, watchTranscriptRun } from "@/lib/api/speaking-transcript";
import { apiRequest } from "@/lib/api/client";
vi.mock("@/lib/api/client", () => ({ API_BASE_URL: "https://fixture.test/api/v1", apiRequest: vi.fn() }));
class FakeSource {
  static items: FakeSource[] = [];
  handlers: Record<string, (event: MessageEvent) => void> = {};
  close = vi.fn(); onerror: (() => void) | null = null;
  constructor(public url: string) { FakeSource.items.push(this); }
  addEventListener(type: string, callback: (event: MessageEvent) => void) { this.handlers[type] = callback; }
  emit(sequence: number) { this.handlers["response.updated"]({ data: JSON.stringify({ sequence, event_type: "response.updated", payload: {} }) } as MessageEvent); }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeSource.items = []; vi.clearAllMocks(); });
it("accepts partial lexical responses without dropping available transcript text", () => {
  const response = { response_id: "33333333-3333-4333-8333-333333333333", status: "PARTIAL", verbatim: "Fictional partial speech", clean: null, words: [], error_code: null, source_audio_fingerprint: "fictional" };
  const parsed = transcriptRunSchema.parse({ run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "fixture", status: "PARTIAL", last_sequence: 1, created_at: "now", responses: [response] });
  expect(parsed.responses[0].status).toBe("PARTIAL"); expect(parsed.responses[0].verbatim).toBe("Fictional partial speech");
});
it("ignores duplicate/older events, reconciles JSON and resumes observation without cancelling work", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource);
  const snapshot = vi.fn(); const event = vi.fn();
  vi.mocked(apiRequest).mockResolvedValue({ run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "key", last_sequence: 2, created_at: "now", status: "RUNNING", responses: [] });
  const stop = watchTranscriptRun("attempt", "run", { event, snapshot, error: vi.fn() });
  FakeSource.items[0].emit(2); FakeSource.items[0].emit(2); FakeSource.items[0].emit(1);
  await vi.advanceTimersByTimeAsync(0); expect(event).toHaveBeenCalledTimes(1); expect(snapshot).toHaveBeenCalledOnce();
  FakeSource.items[0].onerror?.(); await vi.advanceTimersByTimeAsync(1500);
  expect(FakeSource.items.at(-1)?.url).toContain("after=2"); stop();
  expect(FakeSource.items.at(-1)?.close).toHaveBeenCalled(); expect(vi.mocked(apiRequest).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
it("ignores a stale terminal snapshot while a newer event awaits reconciliation", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource);
  const snapshot = vi.fn();
  const base = { run_id: "11111111-1111-4111-8111-111111111111", attempt_id: "22222222-2222-4222-8222-222222222222", cache_key: "key", created_at: "now", responses: [] };
  vi.mocked(apiRequest).mockResolvedValueOnce({ ...base, status: "COMPLETED", last_sequence: 1 }).mockResolvedValue({ ...base, status: "RUNNING", last_sequence: 2 });
  const stop = watchTranscriptRun("attempt", "run", { event: vi.fn(), snapshot, error: vi.fn() });
  FakeSource.items[0].emit(2); await vi.advanceTimersByTimeAsync(0);
  expect(snapshot).not.toHaveBeenCalled(); expect(FakeSource.items[0].close).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(250); expect(snapshot).toHaveBeenCalledOnce(); stop();
});
