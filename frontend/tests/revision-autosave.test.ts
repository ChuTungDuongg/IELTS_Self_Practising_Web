import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RevisionAutosaveQueue, useRevisionAutosave } from "@/features/exam/revision-autosave";
import { saveAnswer } from "@/lib/api/attempts";
import { ApiError, resetAuthRequestStateForTests } from "@/lib/api/client";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

describe("RevisionAutosaveQueue", () => {
  afterEach(() => vi.useRealTimers());

  it("blocks a conflicted key and submission flush while other keys can save", async () => {
    const conflict = new ApiError("ATTEMPT_RESPONSE_CONFLICT", "Changed elsewhere", 409);
    const send = vi.fn((key: string) => key === "q1" ? Promise.reject(conflict) : Promise.resolve());
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "local answer");
    await expect(queue.saveNow("q1")).rejects.toBe(conflict);
    expect(queue.status).toBe("conflict");
    queue.markDirty("q1", "newer local answer");
    await expect(queue.flush()).rejects.toBe(conflict);
    expect(send).toHaveBeenCalledTimes(1);
    expect(queue.hasUnsaved).toBe(true);
    queue.markDirty("q2", "independent answer");
    await queue.saveNow("q2");
    expect(send).toHaveBeenCalledWith("q2", "independent answer");
    expect(queue.status).toBe("conflict");
    queue.stop();
  });

  it("replays an ambiguously failed value before sending a newer local edit", async () => {
    const first = deferred<void>();
    const send = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "older");
    const saving = queue.saveNow("q1");
    queue.markDirty("q1", "newer");
    first.reject(new ApiError("NETWORK_ERROR", "response lost", 0));
    await saving;
    expect(send.mock.calls).toEqual([["q1", "older"], ["q1", "older"], ["q1", "newer"]]);
    expect(queue.status).toBe("saved");
    queue.stop();
  });

  it("does not retry an in-flight failure while offline and sends the latest edit once online", async () => {
    const first = deferred<void>();
    const send = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "older");
    const saving = queue.saveNow("q1");
    queue.markDirty("q1", "newer");
    queue.setOffline(true);
    first.reject(new ApiError("NETWORK_ERROR", "connection lost", 0));
    await saving;
    expect(send).toHaveBeenCalledTimes(1);
    expect(queue.hasUnsaved).toBe(true);
    queue.setOffline(false);
    await queue.flush();
    expect(send.mock.calls).toEqual([["q1", "older"], ["q1", "newer"]]);
    queue.stop();
  });

  it("ignores a late acknowledgement after the queue stops", async () => {
    const pending = deferred<void>();
    const onAcknowledged = vi.fn();
    const queue = new RevisionAutosaveQueue<string>(
      vi.fn().mockReturnValue(pending.promise), 400, { onAcknowledged },
    );
    queue.markDirty("q1", "answer");
    const saving = queue.saveNow("q1");
    queue.stop();
    pending.resolve();
    await saving;
    expect(onAcknowledged).not.toHaveBeenCalled();
  });

  it("keeps a newer edit dirty until its own acknowledgement and coalesces intermediate edits", async () => {
    vi.useFakeTimers();
    const first = deferred<void>();
    const latest = deferred<void>();
    const send = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(latest.promise);
    const queue = new RevisionAutosaveQueue<string>(send, 400);

    queue.markDirty("q1", "A");
    expect(queue.status).toBe("dirty");
    const saving = queue.saveNow("q1");
    expect(queue.status).toBe("saving");
    queue.markDirty("q1", "B");
    queue.markDirty("q1", "C");
    queue.markDirty("q1", "D");
    first.resolve();
    await Promise.resolve();
    expect(queue.status).not.toBe("saved");
    expect(send).toHaveBeenCalledTimes(2);
    expect(send).toHaveBeenLastCalledWith("q1", "D");
    latest.resolve();
    await saving;
    expect(queue.status).toBe("saved");
    expect(queue.hasUnsaved).toBe(false);
    queue.stop();
  });

  it("does not show an old failure after a newer revision succeeds", async () => {
    const old = deferred<void>();
    const send = vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(undefined);
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "old");
    const saving = queue.saveNow("q1");
    queue.markDirty("q1", "new");
    old.reject(new Error("old request failed"));
    await saving;
    expect(send).toHaveBeenLastCalledWith("q1", "new");
    expect(queue.status).toBe("saved");
    queue.stop();
  });

  it("retains a failed latest revision for explicit retry and makes flush throw", async () => {
    const send = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(undefined);
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "latest");
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(queue.status).toBe("error");
    expect(queue.hasUnsaved).toBe(true);
    await queue.flush();
    expect(send).toHaveBeenCalledTimes(2);
    expect(send).toHaveBeenLastCalledWith("q1", "latest");
    expect(queue.status).toBe("saved");
    queue.stop();
  });

  it("flush waits for an in-flight save, sends the latest value, and lets different keys save independently", async () => {
    const q1First = deferred<void>();
    const q1Latest = deferred<void>();
    const q2 = deferred<void>();
    const send = vi.fn((key: string, value: string) => {
      if (key === "q2") return q2.promise;
      return value === "A" ? q1First.promise : q1Latest.promise;
    });
    const queue = new RevisionAutosaveQueue<string>(send, 400);
    queue.markDirty("q1", "A");
    void queue.saveNow("q1");
    queue.markDirty("q1", "D");
    queue.markDirty("q2", "X");
    let completed = false;
    const flush = queue.flush().then(() => { completed = true; });
    expect(send).toHaveBeenCalledWith("q2", "X");
    expect(completed).toBe(false);
    q2.resolve();
    await Promise.resolve();
    expect(completed).toBe(false);
    q1First.resolve();
    await Promise.resolve();
    expect(send).toHaveBeenCalledWith("q1", "D");
    expect(completed).toBe(false);
    q1Latest.resolve();
    await flush;
    expect(queue.status).toBe("saved");
    queue.stop();
  });

  it("keeps the aggregate status dirty while another key is unsaved", async () => {
    const queue = new RevisionAutosaveQueue<string>(vi.fn().mockResolvedValue(undefined), 400);
    queue.markDirty("q1", "A");
    await queue.saveNow("q1");
    queue.markDirty("q2", "B");
    expect(queue.status).toBe("dirty");
    await queue.flush();
    expect(queue.status).toBe("saved");
    queue.stop();
  });

  it("keeps autosave active after React Strict Mode replays effects", async () => {
    vi.useFakeTimers();
    const send = vi.fn().mockResolvedValue(undefined);
    const { result, unmount } = renderHook(() => useRevisionAutosave<string>(send, 400), {
      wrapper: StrictMode,
    });
    act(() => result.current.queue.markDirty("q1", "latest"));
    await act(async () => { vi.advanceTimersByTime(400); });
    expect(send).toHaveBeenCalledWith("q1", "latest");
    unmount();
    await act(async () => { vi.advanceTimersByTime(0); });
  });

  it("saves the same answer after an access-token refresh", async () => {
    resetAuthRequestStateForTests();
    const attemptId = "11111111-1111-4111-8111-111111111111";
    const questionId = "22222222-2222-4222-8222-222222222222";
    let saves = 0;
    const fetchMock = vi.fn((input: string | URL | Request, _init?: RequestInit) => {
      void _init;
      if (String(input).endsWith("/auth/refresh")) return Promise.resolve(new Response(null, { status: 204 }));
      saves += 1;
      return Promise.resolve(saves === 1
        ? new Response(JSON.stringify({ code: "TOKEN_EXPIRED" }), { status: 401 })
        : new Response(JSON.stringify({
          question_id: questionId, value: "TRUE", is_correct: null,
          saved_at: new Date().toISOString(), revision: 1,
        })));
    });
    vi.stubGlobal("fetch", fetchMock);
    const queue = new RevisionAutosaveQueue<string>(
      (_key, answer) => saveAnswer(attemptId, questionId, answer, 0), 400,
    );
    try {
      queue.markDirty(questionId, "TRUE");
      await queue.saveNow(questionId);
      expect(queue.status).toBe("saved");
      expect(queue.hasUnsaved).toBe(false);
      expect(saves).toBe(2);
      const writes = fetchMock.mock.calls.filter(([url]) => String(url).includes("/answers/"));
      expect(writes).toHaveLength(2);
      expect(writes[0][1]?.body).toBe(writes[1][1]?.body);
      expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/auth/refresh"))).toHaveLength(1);
    } finally {
      queue.stop();
      vi.unstubAllGlobals();
    }
  });
});
