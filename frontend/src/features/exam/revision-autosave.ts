"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";

export type AutosaveStatus = "saved" | "dirty" | "saving" | "error" | "conflict";

type Entry<Value> = {
  value: Value;
  revision: number;
  savedRevision: number;
  failed: boolean;
  conflictError: ApiError | null;
  timer: ReturnType<typeof setTimeout> | null;
  worker: Promise<void> | null;
};

export type AutosaveCallbacks<Value> = {
  onDirty?: (key: string, value: Value) => void;
  onAcknowledged?: (key: string, currentValue: Value, isLatest: boolean, result: unknown) => void;
};

export class RevisionAutosaveQueue<Value> {
  private readonly entries = new Map<string, Entry<Value>>();
  private readonly listeners = new Set<(status: AutosaveStatus) => void>();
  private stopped = false;
  private offline = false;

  constructor(
    private readonly send: (key: string, value: Value) => Promise<unknown>,
    private readonly debounceMs: number,
    private readonly callbacks: AutosaveCallbacks<Value> = {},
  ) {}

  get status(): AutosaveStatus {
    const entries = [...this.entries.values()];
    if (entries.some((entry) => entry.conflictError)) return "conflict";
    if (entries.some((entry) => entry.failed && entry.revision > entry.savedRevision)) return "error";
    if (entries.some((entry) => entry.worker)) return "saving";
    if (entries.some((entry) => entry.revision > entry.savedRevision)) return "dirty";
    return "saved";
  }

  get hasUnsaved(): boolean {
    if (this.stopped) return false;
    return [...this.entries.values()].some(
      (entry) => entry.worker || entry.revision > entry.savedRevision,
    );
  }

  subscribe(listener: (status: AutosaveStatus) => void): () => void {
    this.listeners.add(listener);
    listener(this.status);
    return () => { this.listeners.delete(listener); };
  }

  markDirty(key: string, value: Value): void {
    if (this.stopped) return;
    const entry = this.entries.get(key) ?? {
      value,
      revision: 0,
      savedRevision: 0,
      failed: false,
      conflictError: null,
      timer: null,
      worker: null,
    };
    entry.value = value;
    entry.revision += 1;
    if (!entry.conflictError) entry.failed = false;
    this.entries.set(key, entry);
    if (entry.timer) clearTimeout(entry.timer);
    this.callbacks.onDirty?.(key, value);
    if (!entry.conflictError && !this.offline) {
      entry.timer = setTimeout(() => {
        entry.timer = null;
        void this.saveNow(key).catch(() => undefined);
      }, this.debounceMs);
    }
    this.notify();
  }

  async saveNow(key: string): Promise<void> {
    const entry = this.entries.get(key);
    if (!entry || this.stopped) return;
    if (entry.conflictError) throw entry.conflictError;
    if (entry.timer) clearTimeout(entry.timer);
    entry.timer = null;
    if (entry.worker) return entry.worker;
    if (entry.revision === entry.savedRevision) return;
    if (this.offline) throw new ApiError("NETWORK_ERROR", "Offline — changes are kept in this tab.", 0);

    const worker = this.drain(key, entry);
    entry.worker = worker;
    this.notify();
    void worker.then(
      () => { if (entry.worker === worker) { entry.worker = null; this.notify(); } },
      () => { if (entry.worker === worker) { entry.worker = null; this.notify(); } },
    );
    return worker;
  }

  async flush(): Promise<void> {
    for (const entry of this.entries.values()) {
      if (entry.timer) clearTimeout(entry.timer);
      entry.timer = null;
    }
    for (;;) {
      if (this.stopped) throw new Error("This autosave queue has stopped.");
      const conflict = [...this.entries.values()].find((entry) => entry.conflictError)?.conflictError;
      if (conflict) throw conflict;
      if (!this.hasUnsaved) return;
      if (this.offline) throw new ApiError("NETWORK_ERROR", "Offline — changes are kept in this tab.", 0);
      const pending = [...this.entries]
        .filter(([, entry]) => entry.worker || entry.revision > entry.savedRevision)
        .map(([key]) => this.saveNow(key));
      try {
        await Promise.all(pending);
      } catch (error) {
        if ([...this.entries.values()].some((entry) => entry.conflictError)) throw error;
        if ([...this.entries.values()].some(
          (entry) => entry.failed && entry.revision > entry.savedRevision,
        )) throw error;
        // The failed request was superseded while it settled; flush the newer revision.
        await Promise.resolve();
      }
    }
  }

  stop(): void {
    this.stopped = true;
    for (const entry of this.entries.values()) {
      if (entry.timer) clearTimeout(entry.timer);
      entry.timer = null;
    }
  }

  setOffline(offline: boolean): void {
    this.offline = offline;
    if (offline) {
      for (const entry of this.entries.values()) {
        if (entry.timer) clearTimeout(entry.timer);
        entry.timer = null;
      }
    }
  }

  private async drain(key: string, entry: Entry<Value>): Promise<void> {
    while (!this.stopped && entry.revision > entry.savedRevision) {
      if (this.offline) return;
      const revision = entry.revision;
      const value = entry.value;
      entry.failed = false;
      this.notify();
      try {
        const result = await this.send(key, value);
        entry.savedRevision = Math.max(entry.savedRevision, revision);
        if (!this.stopped) this.callbacks.onAcknowledged?.(key, entry.value, entry.revision === revision, result);
      } catch (error) {
        if (error instanceof ApiError && error.code === "ATTEMPT_RESPONSE_CONFLICT") {
          entry.conflictError = error;
          if (entry.timer) clearTimeout(entry.timer);
          entry.timer = null;
          this.notify();
          throw error;
        }
        if (!this.stopped && !this.offline && entry.revision !== revision && error instanceof ApiError
          && (error.code === "NETWORK_ERROR" || error.status >= 500)) {
          // The server may have committed the older value. A same-payload replay
          // obtains its revision before the newer local value is sent.
          try {
            const result = await this.send(key, value);
            entry.savedRevision = Math.max(entry.savedRevision, revision);
            if (!this.stopped) this.callbacks.onAcknowledged?.(key, entry.value, entry.revision === revision, result);
            this.notify();
            continue;
          } catch (retryError) {
            if (retryError instanceof ApiError && retryError.code === "ATTEMPT_RESPONSE_CONFLICT") {
              entry.conflictError = retryError;
              if (entry.timer) clearTimeout(entry.timer);
              entry.timer = null;
            } else {
              entry.failed = true;
            }
            this.notify();
            throw retryError;
          }
        }
        if (entry.revision === revision) {
          entry.failed = true;
          this.notify();
          throw error;
        }
        // A newer local value supersedes this failed request.
      }
      this.notify();
    }
  }

  private notify(): void {
    const status = this.status;
    this.listeners.forEach((listener) => listener(status));
  }
}

export function useRevisionAutosave<Value>(
  send: (key: string, value: Value) => Promise<unknown>,
  debounceMs: number,
  callbacks?: AutosaveCallbacks<Value>,
  pauseWhileOffline = false,
) {
  const queue = useMemo(() => {
    const created = new RevisionAutosaveQueue<Value>(send, debounceMs, callbacks);
    if (pauseWhileOffline && typeof navigator !== "undefined") created.setOffline(navigator.onLine === false);
    return created;
  }, [send, debounceMs, callbacks, pauseWhileOffline]);
  const pendingStop = useRef<{
    queue: RevisionAutosaveQueue<Value>;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);
  const [status, setStatus] = useState<AutosaveStatus>(queue.status);
  const [offline, setOffline] = useState(() => pauseWhileOffline && typeof navigator !== "undefined" && navigator.onLine === false);

  useEffect(() => queue.subscribe(setStatus), [queue]);
  useEffect(() => {
    if (!pauseWhileOffline) return;
    const wentOffline = () => { queue.setOffline(true); setOffline(true); };
    const wentOnline = () => {
      queue.setOffline(false);
      setOffline(false);
      void queue.flush().catch(() => undefined);
    };
    window.addEventListener("offline", wentOffline);
    window.addEventListener("online", wentOnline);
    return () => {
      window.removeEventListener("offline", wentOffline);
      window.removeEventListener("online", wentOnline);
    };
  }, [pauseWhileOffline, queue]);
  useEffect(() => {
    if (pendingStop.current?.queue === queue) {
      clearTimeout(pendingStop.current.timer);
      pendingStop.current = null;
    }
    return () => {
      // Strict Mode replays this cleanup immediately; the following setup cancels the stop.
      pendingStop.current = { queue, timer: setTimeout(() => queue.stop(), 0) };
    };
  }, [queue]);
  useEffect(() => {
    if (status === "saved") return;
    const warn = (event: BeforeUnloadEvent) => {
      if (!queue.hasUnsaved) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [queue, status]);

  return { queue, status, offline };
}
