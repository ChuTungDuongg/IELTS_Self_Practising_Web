import { afterEach, expect, it, vi } from "vitest";
import { cancelSpeakingAIRun, createSpeakingAIRun, latestSpeakingAIRun, speakingAIRunSchema, watchSpeakingAIRun } from "@/lib/api/speaking-ai";
import { apiRequest } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({ API_BASE_URL: "https://fixture.test/api/v1", apiRequest: vi.fn() }));
const runId = "11111111-1111-4111-8111-111111111111";
const attemptId = "22222222-2222-4222-8222-222222222222";
const criterion = { status: "WAITING", score: null, feedback_status: "PENDING", feedback: null, strengths: [], improvements: [], error_code: null, evidence_summary: {} };
const base = { run_id: runId, attempt_id: attemptId, cache_key: "fixture", created_at: "now", status: "RUNNING", stage: "SCORING", last_sequence: 2, advisory: true, raw_mean: null, overall_band: null, criteria: { fc: criterion, lr: criterion, gra: criterion, pr: criterion }, error_code: null, summary: { responses: [] } };
class FakeSource {
  static items: FakeSource[] = [];
  handlers: Record<string, (event: MessageEvent) => void> = {};
  close = vi.fn(); onerror: (() => void) | null = null;
  constructor(public url: string, public options: EventSourceInit) { FakeSource.items.push(this); }
  addEventListener(type: string, callback: (event: MessageEvent) => void) { this.handlers[type] = callback; }
  emit(sequence: number, type = "criterion.score") { this.handlers[type]({ data: JSON.stringify({ sequence, event_type: type, payload: { criterion: "fc" } }) } as MessageEvent); }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); FakeSource.items = []; vi.clearAllMocks(); });
it("creates grading independently of transcript and keeps cancellation explicit", async () => {
  vi.mocked(apiRequest).mockResolvedValueOnce({ run_id: runId, cache_hit: false, existing_active: true }).mockResolvedValueOnce(base).mockResolvedValueOnce({ run: base });
  await createSpeakingAIRun(attemptId); await cancelSpeakingAIRun(attemptId, runId); await latestSpeakingAIRun(attemptId);
  expect(apiRequest).toHaveBeenNthCalledWith(1, `/speaking-attempts/${attemptId}/ai-runs`, { method: "POST" });
  expect(apiRequest).toHaveBeenNthCalledWith(2, `/speaking-attempts/${attemptId}/ai-runs/${runId}/cancel`, { method: "POST" });
});
it("rejects non-half bands and a non-advisory result without fabricating a default", () => {
  expect(speakingAIRunSchema.safeParse({ ...base, criteria: { ...base.criteria, fc: { ...criterion, score: 6.3 } } }).success).toBe(false);
  expect(speakingAIRunSchema.safeParse({ ...base, advisory: false }).success).toBe(false);
});
it("suppresses replay, reconciles scores, reconnects with cursor and closes observation without cancellation", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource); vi.mocked(apiRequest).mockResolvedValue(base);
  const event = vi.fn(); const snapshot = vi.fn(); const stop = watchSpeakingAIRun(attemptId, runId, { event, snapshot, error: vi.fn() });
  const first = FakeSource.items[0]; first.emit(2); first.emit(2); first.emit(1);
  await vi.advanceTimersByTimeAsync(0); expect(event).toHaveBeenCalledOnce(); expect(snapshot).toHaveBeenCalledOnce();
  first.onerror?.(); await vi.advanceTimersByTimeAsync(1500);
  expect(FakeSource.items.at(-1)?.url).toContain("after=2"); expect(FakeSource.items.at(-1)?.options).toEqual({ withCredentials: true });
  stop(); expect(FakeSource.items.at(-1)?.close).toHaveBeenCalled();
  expect(vi.mocked(apiRequest).mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
it("rejects a stale terminal snapshot and reconciles the newer sequence", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource);
  vi.mocked(apiRequest).mockResolvedValueOnce({ ...base, last_sequence: 1, status: "COMPLETED", stage: "COMPLETED" }).mockResolvedValue(base);
  const snapshot = vi.fn(); const stop = watchSpeakingAIRun(attemptId, runId, { event: vi.fn(), snapshot, error: vi.fn() });
  FakeSource.items[0].emit(2); await vi.advanceTimersByTimeAsync(0);
  expect(snapshot).not.toHaveBeenCalled(); expect(FakeSource.items[0].close).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(250); expect(snapshot).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ status: "RUNNING" })); stop();
});
it("retries JSON after connection failure and closes on reconciled terminal state", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource);
  vi.mocked(apiRequest).mockRejectedValueOnce(new Error("private provider error")).mockResolvedValue({ ...base, status: "COMPLETED", stage: "COMPLETED", last_sequence: 3 });
  const error = vi.fn(); const snapshot = vi.fn(); const stop = watchSpeakingAIRun(attemptId, runId, { event: vi.fn(), snapshot, error });
  FakeSource.items[0].onerror?.(); await vi.advanceTimersByTimeAsync(0); expect(error).toHaveBeenCalledOnce();
  await vi.advanceTimersByTimeAsync(5000); expect(snapshot).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ status: "COMPLETED" }));
  expect(FakeSource.items).toHaveLength(1); stop();
});
it("ignores malformed events and late requests after cleanup", async () => {
  vi.useFakeTimers(); vi.stubGlobal("EventSource", FakeSource);
  let finish!: (value: unknown) => void; vi.mocked(apiRequest).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const snapshot = vi.fn(); const error = vi.fn(); const stop = watchSpeakingAIRun(attemptId, runId, { event: vi.fn(), snapshot, error });
  FakeSource.items[0].handlers["criterion.score"]({ data: "private garbage" } as MessageEvent); expect(error).toHaveBeenCalledOnce(); stop();
  finish(base); await vi.advanceTimersByTimeAsync(0); expect(snapshot).not.toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});
