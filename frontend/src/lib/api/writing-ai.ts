import { z } from "zod";
import { API_BASE_URL, apiRequest } from "./client";

export const aiTraits = ["ta", "cc", "lr", "gra"] as const;
export type AITrait = typeof aiTraits[number];
export const aiTraitNames: Record<AITrait, string> = {
  ta: "Task Response", cc: "Coherence & Cohesion", lr: "Lexical Resource",
  gra: "Grammatical Range & Accuracy",
};
const band = z.number().min(0).max(9).multipleOf(0.5);
const evidence = z.object({ quote: z.string().min(1).max(600), assessment: z.string().min(1).max(800) });
export const aiCriterionSchema = z.object({
  score: band, feedback: z.string().min(1).max(2000),
  strengths: z.array(z.string().min(1).max(800)).max(5),
  improvements: z.array(z.string().min(1).max(800)).max(5),
  evidence: z.array(evidence).max(6),
});
export type AICriterion = z.infer<typeof aiCriterionSchema>;
const criterion = aiCriterionSchema;
export const aiActivityPhases = ["preparing", "starting_model", "collecting_evidence", "validating_evidence", "evidence_collected", "scoring", "validating_score", "retrying", "completed", "failed"] as const;
export const aiActivitySchema = z.object({
  phase: z.enum(aiActivityPhases), criterion: z.enum(aiTraits).nullable(),
  stage: z.enum(["evidence", "scoring"]).nullable(), started_at: z.string(),
});
export type AIActivity = z.infer<typeof aiActivitySchema>;
export const aiWritingResultSchema = z.object({
  criteria: z.object({ ta: criterion, cc: criterion, lr: criterion, gra: criterion }),
  raw_mean: z.number().min(0).max(9), overall_band: band,
});
export type AIWritingResult = z.infer<typeof aiWritingResultSchema>;
export const aiRunSchema = z.object({
  id: z.string().uuid(), attempt_id: z.string().uuid(), writing_task_id: z.string().uuid(),
  status: z.enum(["PENDING", "RUNNING", "COMPLETED", "FAILED"]),
  provider: z.string(), model: z.string(), prompt_version: z.string(),
  result: aiWritingResultSchema.nullable(), progress: z.partialRecord(z.enum(aiTraits), criterion),
  error_code: z.string().nullable(), error_message: z.string().nullable(),
  started_at: z.string().nullable(), completed_at: z.string().nullable(), created_at: z.string(),
  activity: aiActivitySchema.nullable().optional(),
});
export type AIWritingRun = z.infer<typeof aiRunSchema>;
export const aiEventTypes = ["run.started", "provider.starting", "provider.ready", "criterion.started", "evidence.request.started", "evidence.validation.started", "criterion.evidence.completed", "criterion.scoring.started", "criterion.scoring.validation.started", "criterion.retrying", "criterion.completed", "run.completed", "run.failed", "heartbeat"] as const;
export const aiEventSchema = z.object({
  sequence: z.number().int().positive(), event_type: z.enum(aiEventTypes),
  created_at: z.string().optional(),
  payload: z.object({
    criterion: z.enum(aiTraits).nullable().optional(),
    stage: z.enum(["evidence", "scoring"]).nullable().optional(),
    evidence: z.array(evidence).max(6).nullable().optional(),
    result: criterion.nullable().optional(), error_code: z.string().nullable().optional(),
    error_message: z.string().nullable().optional(),
  }),
});
export type AIWritingEvent = z.infer<typeof aiEventSchema>;

export async function listAIWritingRuns(attemptId: string, taskId: string) {
  return z.object({ configured: z.boolean(), items: z.array(aiRunSchema) }).parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/writing/${taskId}/ai-grading-runs`),
  );
}
export async function createAIWritingRun(attemptId: string, taskId: string, force = false) {
  return z.object({ run_id: z.string().uuid(), cache_hit: z.boolean(), existing_active: z.boolean() }).parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/writing/${taskId}/ai-grading-runs`, {
      method: "POST", body: JSON.stringify({ force }),
    }),
  );
}
export async function getAIWritingRun(runId: string) {
  return aiRunSchema.parse(await apiRequest<unknown>(`/ai-writing-grading-runs/${runId}`));
}
export function isActiveAIRun(run: AIWritingRun | null) {
  return run?.status === "PENDING" || run?.status === "RUNNING";
}

// Uses the application's cookie auth. A JSON probe refreshes expired access
// cookies before reconnecting; providers are never browser clients.
export function watchAIWritingRun(runId: string, callbacks: {
  event: (event: AIWritingEvent) => void;
  snapshot: (run: AIWritingRun) => void;
  error: (message: string) => void;
}) {
  let stopped = false;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let after = 0;
  let reconciling = false;

  async function reconcile() {
    if (stopped || reconciling) return;
    reconciling = true;
    source?.close();
    try {
      const run = await getAIWritingRun(runId);
      if (stopped) return;
      callbacks.snapshot(run);
      if (isActiveAIRun(run)) timer = setTimeout(connect, 1500);
    } catch {
      if (!stopped) {
        callbacks.error("Mất kết nối tiến trình chấm. Đang kết nối lại…");
        timer = setTimeout(reconcile, 5000);
      }
    } finally { reconciling = false; }
  }
  function connect() {
    if (stopped) return;
    source = new EventSource(`${API_BASE_URL}/ai-writing-grading-runs/${runId}/events?after=${after}`, { withCredentials: true });
    for (const type of aiEventTypes) source.addEventListener(type, (message) => {
      if (stopped) return;
      try {
        const event = aiEventSchema.parse(JSON.parse((message as MessageEvent).data));
        if (event.event_type !== type || event.sequence <= after) return;
        after = event.sequence;
        if (type !== "heartbeat") callbacks.event(event);
        if (type === "run.completed" || type === "run.failed") void reconcile();
      } catch { callbacks.error("Không thể đọc tiến trình chấm. Đang khôi phục kết quả đã lưu…"); void reconcile(); }
    });
    source.onerror = () => { void reconcile(); };
  }
  connect();
  return () => { stopped = true; source?.close(); if (timer) clearTimeout(timer); };
}
