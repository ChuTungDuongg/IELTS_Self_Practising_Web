import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, resetAuthRequestStateForTests } from "@/lib/api/client";
import { cancelAIWritingRun, isCancelledAIRun, watchAIWritingRun } from "@/lib/api/writing-ai";

const runId = "11111111-1111-4111-8111-111111111111";
const cancelled = {
  id: runId, attempt_id: runId, writing_task_id: runId, status: "FAILED",
  provider: "fake", model: "fake", prompt_version: "mts-task2-v7",
  result: null, progress: {}, error_code: "AI_GRADING_CANCELLED", error_message: "Bạn đã dừng bài chấm AI.",
  started_at: null, completed_at: "2026-10-09T00:00:00Z", created_at: "2026-10-09T00:00:00Z",
};

beforeEach(() => resetAuthRequestStateForTests());
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("posts cancellation with normal cookie auth and validates the existing FAILED response", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(cancelled), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const run = await cancelAIWritingRun(runId);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls[0][0]).toBe(`http://localhost:8000/api/v1/ai-writing-grading-runs/${runId}/cancel`);
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", credentials: "include", cache: "no-store" });
  expect(run.status).toBe("FAILED");
  expect(isCancelledAIRun(run)).toBe(true);
  expect(isCancelledAIRun({ ...run, error_code: "AI_PROVIDER_TIMEOUT" })).toBe(false);
});

it("rejects a new database status instead of silently changing the API contract", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...cancelled, status: "CANCELLED" }), { status: 200 })));
  await expect(cancelAIWritingRun(runId)).rejects.toThrow();
});

it("preserves authorization failures from the normal API client", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "AI_RUN_NOT_FOUND", message: "Không tìm thấy bài đánh giá AI này." }), { status: 404 })));
  await expect(cancelAIWritingRun(runId)).rejects.toBeInstanceOf(ApiError);
});

class ObserverSource {
  static instances: ObserverSource[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>();
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { ObserverSource.instances.push(this); }
  addEventListener(type: string, callback: (event: MessageEvent) => void) { this.listeners.set(type, callback); }
  emit(type: string, sequence: number) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify({ sequence, event_type: type, payload: {} }) }));
  }
}

function observer() {
  ObserverSource.instances = [];
  vi.stubGlobal("EventSource", ObserverSource);
  const callbacks = { event: vi.fn(), snapshot: vi.fn(), error: vi.fn() };
  return { callbacks, stop: watchAIWritingRun(runId, callbacks) };
}

it("retires a disconnected source before probing and ignores its late callbacks after reconnect", async () => {
  vi.useFakeTimers();
  const active = { ...cancelled, status: "RUNNING", error_code: null, error_message: null, completed_at: null };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(active), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const { callbacks, stop } = observer();
  try {
    const old = ObserverSource.instances[0];
    old.emit("criterion.started", 4);
    old.onerror?.();
    await vi.advanceTimersByTimeAsync(1500);
    expect(ObserverSource.instances).toHaveLength(2);
    expect(ObserverSource.instances[1].url).toContain("after=4");
    expect(old.close).toHaveBeenCalledOnce();
    callbacks.event.mockClear();
    old.emit("run.failed", 99);
    old.onerror?.();
    expect(callbacks.event).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
    ObserverSource.instances[1].emit("criterion.started", 5);
    expect(callbacks.event).toHaveBeenCalledOnce();
  } finally { stop(); }
});

it("stops only observation and drops an in-flight snapshot after cleanup", async () => {
  vi.useFakeTimers();
  let resolveProbe!: (response: Response) => void;
  const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { resolveProbe = resolve; }));
  vi.stubGlobal("fetch", fetchMock);
  const { callbacks, stop } = observer();
  const source = ObserverSource.instances[0];
  source.onerror?.();
  stop();
  resolveProbe(new Response(JSON.stringify(cancelled), { status: 200 }));
  await vi.advanceTimersByTimeAsync(10_000);
  source.emit("run.failed", 10);
  source.onerror?.();
  expect(source.close).toHaveBeenCalledOnce();
  expect(ObserverSource.instances).toHaveLength(1);
  expect(callbacks.event).not.toHaveBeenCalled();
  expect(callbacks.snapshot).not.toHaveBeenCalled();
  expect(callbacks.error).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock.mock.calls[0][0]).toBe(`http://localhost:8000/api/v1/ai-writing-grading-runs/${runId}`);
  expect(fetchMock.mock.calls[0][1].method).toBeUndefined();
  expect(fetchMock.mock.calls[0][1].signal).toBeUndefined();
});
