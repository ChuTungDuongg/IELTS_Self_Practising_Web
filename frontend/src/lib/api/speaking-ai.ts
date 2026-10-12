import { z } from "zod";
import { API_BASE_URL, apiRequest } from "./client";

const bandSchema = z.number().min(0).max(9).multipleOf(0.5);
const safeMetrics = z.record(z.string().max(80), z.json()).refine((value) => JSON.stringify(value).length <= 16000, "Evidence summary exceeds limit");
const criterionSchema = z.object({
  status: z.enum(["WAITING", "SCORING", "SCORED", "COMPLETED", "FAILED", "UNAVAILABLE"]),
  score: bandSchema.nullable(), feedback_status: z.enum(["PENDING", "READY", "FALLBACK"]),
  feedback: z.string().max(1200).nullable(), strengths: z.array(z.string().max(300)).max(6), improvements: z.array(z.string().max(300)).max(6),
  error_code: z.string().max(200).nullable(), evidence_summary: safeMetrics.default({}),
});
const diagnosticSchema = z.object({
  response_id: z.string().uuid(), part_number: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  words_per_minute: z.number().nonnegative().nullable().default(null), part2_sustained_seconds: z.number().nonnegative().nullable().default(null),
  pronunciation_status: z.enum(["AVAILABLE", "LOW_EVIDENCE", "UNAVAILABLE"]),
  mean_alignment_confidence: z.number().min(0).max(1).nullable().default(null), pitch_range_hz: z.number().nonnegative().nullable().default(null),
  limitations: z.array(z.string().max(200)).max(20).default([]),
});
export const speakingAIRunSchema = z.object({
  run_id: z.string().uuid(), attempt_id: z.string().uuid(), cache_key: z.string().max(512), created_at: z.string(),
  status: z.enum(["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]),
  stage: z.enum(["PENDING", "QUALITY_CHECK", "TRANSCRIBING", "ANALYSING_AUDIO", "BUILDING_EVIDENCE", "SCORING", "GENERATING_FEEDBACK", "COMPLETED", "FAILED", "CANCELLED"]),
  last_sequence: z.number().int().nonnegative(), advisory: z.literal(true), raw_mean: z.number().min(0).max(9).nullable(), overall_band: bandSchema.nullable(),
  criteria: z.object({ fc: criterionSchema, lr: criterionSchema, gra: criterionSchema, pr: criterionSchema }), error_code: z.string().max(200).nullable(),
  summary: z.object({ responses: z.array(diagnosticSchema).max(1000).default([]) }).default({ responses: [] }),
});
export type SpeakingAIRun = z.infer<typeof speakingAIRunSchema>;
export type SpeakingAICriterion = keyof SpeakingAIRun["criteria"];
const eventTypes = ["run.queued", "run.stage", "criterion.score", "criterion.feedback", "run.completed", "run.failed", "run.cancelled", "run.recovered", "run.interrupted"] as const;
const eventSchema = z.object({ sequence: z.number().int().positive(), event_type: z.enum(eventTypes), payload: safeMetrics });
export type SpeakingAIEvent = z.infer<typeof eventSchema>;
export const activeSpeakingAI = (run: SpeakingAIRun | null) => run?.status === "PENDING" || run?.status === "RUNNING";
const root = (attemptId: string) => `/speaking-attempts/${encodeURIComponent(attemptId)}/ai-runs`;
export async function createSpeakingAIRun(attemptId: string) {
  return z.object({ run_id: z.string().uuid(), cache_hit: z.boolean(), existing_active: z.boolean() }).parse(await apiRequest(root(attemptId), { method: "POST" }));
}
export async function latestSpeakingAIRun(attemptId: string) { return z.object({ run: speakingAIRunSchema.nullable() }).parse(await apiRequest(root(attemptId))).run; }
export async function getSpeakingAIRun(attemptId: string, runId: string) { return speakingAIRunSchema.parse(await apiRequest(`${root(attemptId)}/${encodeURIComponent(runId)}`)); }
export async function cancelSpeakingAIRun(attemptId: string, runId: string) { return speakingAIRunSchema.parse(await apiRequest(`${root(attemptId)}/${encodeURIComponent(runId)}/cancel`, { method: "POST" })); }

/** Events contain metadata only. Reconcile durable results through JSON; disconnect never cancels. */
export function watchSpeakingAIRun(attemptId: string, runId: string, callbacks: { event(event: SpeakingAIEvent): void; snapshot(run: SpeakingAIRun): void; error(): void }, initialSequence = 0) {
  let stopped = false; let finished = false; let source: EventSource | null = null; let after = initialSequence;
  let timer: ReturnType<typeof setTimeout> | null = null; let synchronizing = false; let again = false; let reconnect = false;
  const closeSource = () => { source?.close(); source = null; };
  function schedule(action: () => void, delay: number) { if (timer) clearTimeout(timer); timer = setTimeout(() => { timer = null; action(); }, delay); }
  async function synchronize() {
    if (stopped || finished) return;
    if (synchronizing) { again = true; return; }
    synchronizing = true;
    try {
      const run = await getSpeakingAIRun(attemptId, runId); if (stopped || finished) return;
      // Even a terminal snapshot can lag a newer event received while GET was in flight.
      if (run.last_sequence < after) { again = true; return; }
      after = run.last_sequence; callbacks.snapshot(run);
      if (!activeSpeakingAI(run)) { finished = true; closeSource(); if (timer) clearTimeout(timer); }
      else if (reconnect) { reconnect = false; schedule(connect, 1500); }
    } catch { if (!stopped && !finished) { callbacks.error(); reconnect = true; schedule(() => void synchronize(), 5000); } }
    finally { synchronizing = false; if (again && !stopped && !finished) { again = false; schedule(() => void synchronize(), 250); } }
  }
  function connect() {
    if (stopped || finished) return;
    closeSource();
    try {
      const connection = new EventSource(`${API_BASE_URL}${root(attemptId)}/${encodeURIComponent(runId)}/events?after=${after}`, { withCredentials: true }); source = connection;
      for (const type of eventTypes) connection.addEventListener(type, (message) => {
        if (stopped || finished || source !== connection) return;
        try {
          const event = eventSchema.parse(JSON.parse((message as MessageEvent).data));
          if (event.event_type !== type || event.sequence <= after) return;
          after = event.sequence; callbacks.event(event); void synchronize();
        } catch { callbacks.error(); void synchronize(); }
      });
      connection.onerror = () => { if (!stopped && !finished && source === connection) { closeSource(); reconnect = true; void synchronize(); } };
    } catch { callbacks.error(); reconnect = true; schedule(() => void synchronize(), 5000); }
  }
  connect();
  return () => { stopped = true; closeSource(); if (timer) clearTimeout(timer); };
}
