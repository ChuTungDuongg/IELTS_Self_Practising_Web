import { z } from "zod";
import { API_BASE_URL, apiRequest } from "./client";

const wordSchema = z.object({ word: z.string().min(1).max(200), start: z.number().nonnegative(), end: z.number().nonnegative(), confidence: z.number().min(0).max(1).nullable().optional() });
export const transcriptRunSchema = z.object({
  run_id: z.string().uuid(), attempt_id: z.string().uuid(), cache_key: z.string(),
  status: z.enum(["PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED"]), last_sequence: z.number().int().nonnegative(), created_at: z.string(),
  responses: z.array(z.object({ response_id: z.string().uuid(), status: z.enum(["WAITING", "PROCESSING", "READY", "FAILED"]), verbatim: z.string().max(60000).nullable(), clean: z.string().max(60000).nullable(), words: z.array(wordSchema).max(10000), error_code: z.string().nullable(), source_audio_fingerprint: z.string() })).max(1000),
});
export type TranscriptRun = z.infer<typeof transcriptRunSchema>;
const eventTypes = ["run.queued", "run.started", "response.updated", "run.completed", "run.interrupted", "run.recovered"] as const;
const eventSchema = z.object({ sequence: z.number().int().positive(), event_type: z.enum(eventTypes), payload: z.record(z.string(), z.string()) });
export type TranscriptEvent = z.infer<typeof eventSchema>;
export const activeTranscript = (run: TranscriptRun | null) => run?.status === "PENDING" || run?.status === "RUNNING";
export async function createTranscriptRun(attemptId: string) {
  return z.object({ run_id: z.string().uuid(), cache_hit: z.boolean(), existing_active: z.boolean() }).parse(await apiRequest(`/speaking-attempts/${attemptId}/transcript-runs`, { method: "POST" }));
}
export async function latestTranscriptRun(attemptId: string) { return z.object({ run: transcriptRunSchema.nullable() }).parse(await apiRequest(`/speaking-attempts/${attemptId}/transcript-runs`)).run; }
export async function getTranscriptRun(attemptId: string, runId: string) { return transcriptRunSchema.parse(await apiRequest(`/speaking-attempts/${attemptId}/transcript-runs/${runId}`)); }

/** Observation only. Cleanup never sends a mutation or cancels backend processing. */
export function watchTranscriptRun(attemptId: string, runId: string, callbacks: { event(event: TranscriptEvent): void; snapshot(run: TranscriptRun): void; error(): void }, initialSequence = 0) {
  let stopped = false; let source: EventSource | null = null; let after = initialSequence;
  let timer: ReturnType<typeof setTimeout> | null = null; let synchronizing = false; let again = false; let reconnect = false;
  const closeSource = () => { source?.close(); source = null; };
  async function synchronize() {
    if (stopped) return;
    if (synchronizing) { again = true; return; }
    synchronizing = true;
    try {
      const run = await getTranscriptRun(attemptId, runId); if (stopped) return;
      if (run.last_sequence < after) { again = true; return; }
      after = run.last_sequence; callbacks.snapshot(run);
      if (!activeTranscript(run)) { closeSource(); reconnect = false; }
      else if (reconnect) { reconnect = false; timer = setTimeout(connect, 1500); }
    } catch { if (!stopped) { callbacks.error(); reconnect = true; timer = setTimeout(synchronize, 5000); } }
    finally { synchronizing = false; if (again && !stopped) { again = false; timer = setTimeout(synchronize, 250); } }
  }
  function connect() {
    if (stopped) return;
    closeSource(); const connection = new EventSource(`${API_BASE_URL}/speaking-attempts/${attemptId}/transcript-runs/${runId}/events?after=${after}`, { withCredentials: true }); source = connection;
    for (const type of eventTypes) connection.addEventListener(type, (message) => {
      if (stopped || source !== connection) return;
      try {
        const event = eventSchema.parse(JSON.parse((message as MessageEvent).data));
        if (event.event_type !== type || event.sequence <= after) return;
        after = event.sequence; callbacks.event(event); void synchronize();
      } catch { callbacks.error(); void synchronize(); }
    });
    connection.onerror = () => { if (!stopped && source === connection) { closeSource(); reconnect = true; void synchronize(); } };
  }
  connect();
  return () => { stopped = true; closeSource(); if (timer) clearTimeout(timer); };
}
