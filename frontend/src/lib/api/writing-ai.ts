import { z } from "zod";
import { API_BASE_URL, apiRequest } from "./client";
import { task1AnalysisSchema } from "./task1-visual";

export const aiTraits = ["ta", "cc", "lr", "gra"] as const;
export type AITrait = typeof aiTraits[number];
export const aiTraitNames: Record<AITrait, string> = {
  ta: "Task Response", cc: "Coherence & Cohesion", lr: "Lexical Resource",
  gra: "Grammatical Range & Accuracy",
};
export function traitNamesForTask(taskNumber: 1 | 2) {
  return taskNumber === 1 ? { ...aiTraitNames, ta: "Task Achievement" } : aiTraitNames;
}
const band = z.number().min(0).max(9).multipleOf(0.5);
const evidence = z.object({ source_id: z.string().max(32).nullable().optional(), quote: z.string().min(1).max(12000), assessment: z.string().min(1).max(800) });
export const aiCriterionSchema = z.object({
  score: band, feedback: z.string().min(1).max(2000),
  strengths: z.array(z.string().min(1).max(800)).max(5),
  improvements: z.array(z.string().min(1).max(800)).max(5),
  evidence: z.array(evidence).max(6),
});
export type AICriterion = z.infer<typeof aiCriterionSchema>;
const criterion = aiCriterionSchema;
export const aiActivityPhases = ["preparing", "starting_model", "collecting_evidence", "validating_evidence", "evidence_collected", "scoring", "validating_score", "retrying", "completed", "failed", "visual_grounding", "visual_grounded", "deriving_facts", "derived_facts_failed", "extracting_claims", "claims_extracted", "verifying_claims", "claims_verified", "claim_extraction_failed", "claim_verification_failed", "chart_cross_check", "chart_read", "chart_fallback", "chart_reconciled"] as const;
const assessmentStage = z.enum(["evidence", "scoring", "visual_grounding", "derived_facts", "claim_extraction", "claim_verification", "chart_cross_check"]);
export const aiActivitySchema = z.object({
  phase: z.enum(aiActivityPhases), criterion: z.enum(aiTraits).nullable(),
  stage: assessmentStage.nullable(), started_at: z.string(),
});
export type AIActivity = z.infer<typeof aiActivitySchema>;
const task2Result = z.object({
  criteria: z.object({ ta: criterion, cc: criterion, lr: criterion, gra: criterion }),
  raw_mean: z.number().min(0).max(9), overall_band: band,
  task_number: z.literal(2).optional(),
});
export const aiWritingResultSchema = z.union([
  task2Result.extend({ task_number: z.literal(1), task1_analysis: task1AnalysisSchema }),
  task2Result,
]);
export type AIWritingResult = z.infer<typeof aiWritingResultSchema>;
const criterionFailure = z.object({
  error_code: z.string().max(80), error_message: z.string().max(300),
  stage: assessmentStage.nullable().optional(),
});
export const aiRunSchema = z.object({
  id: z.string().uuid(), attempt_id: z.string().uuid(), writing_task_id: z.string().uuid(),
  status: z.enum(["PENDING", "RUNNING", "COMPLETED", "FAILED"]),
  provider: z.string(), model: z.string(), prompt_version: z.string(),
  result: aiWritingResultSchema.nullable(), progress: z.partialRecord(z.enum(aiTraits), criterion),
  failures: z.partialRecord(z.enum(aiTraits), criterionFailure).optional(),
  error_code: z.string().nullable(), error_message: z.string().nullable(),
  started_at: z.string().nullable(), completed_at: z.string().nullable(), created_at: z.string(),
  activity: aiActivitySchema.nullable().optional(),
  task_number: z.union([z.literal(1), z.literal(2)]).optional(),
  task1_analysis: task1AnalysisSchema.nullable().optional(),
});
export type AIWritingRun = z.infer<typeof aiRunSchema>;
export const aiEventTypes = ["run.started", "provider.starting", "provider.ready", "criterion.started", "evidence.request.started", "evidence.validation.started", "criterion.evidence.completed", "criterion.scoring.started", "criterion.scoring.validation.started", "criterion.retrying", "criterion.completed", "criterion.failed", "run.completed", "run.failed", "heartbeat", "visual_grounding.started", "visual_grounding.completed", "visual_grounding.failed", "derived_facts.completed", "derived_facts.failed", "claim_extraction.started", "claim_extraction.completed", "claim_extraction.failed", "claim_verification.started", "claim_verification.completed", "claim_verification.failed", "chart_specialist.started", "chart_specialist.completed", "chart_specialist.failed", "chart_reconciliation.completed"] as const;
export const aiEventSchema = z.object({
  sequence: z.number().int().positive(), event_type: z.enum(aiEventTypes),
  created_at: z.string().optional(),
  payload: z.object({
    criterion: z.enum(aiTraits).nullable().optional(),
    stage: assessmentStage.nullable().optional(),
    evidence: z.array(evidence).max(6).nullable().optional(),
    result: criterion.nullable().optional(), error_code: z.string().nullable().optional(),
    error_message: z.string().nullable().optional(),
    task1_analysis: task1AnalysisSchema.nullable().optional(),
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
export async function cancelAIWritingRun(runId: string) {
  return aiRunSchema.parse(await apiRequest<unknown>(`/ai-writing-grading-runs/${runId}/cancel`, { method: "POST" }));
}
export function isActiveAIRun(run: AIWritingRun | null) {
  return run?.status === "PENDING" || run?.status === "RUNNING";
}
export function isCancelledAIRun(run: AIWritingRun | null) {
  return run?.status === "FAILED" && run.error_code === "AI_GRADING_CANCELLED";
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

  function closeSource() {
    const previous = source;
    source = null;
    previous?.close();
  }

  async function reconcile() {
    if (stopped || reconciling) return;
    reconciling = true;
    closeSource();
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
    const connection = new EventSource(`${API_BASE_URL}/ai-writing-grading-runs/${runId}/events?after=${after}`, { withCredentials: true });
    source = connection;
    for (const type of aiEventTypes) connection.addEventListener(type, (message) => {
      if (stopped || source !== connection) return;
      try {
        const event = aiEventSchema.parse(JSON.parse((message as MessageEvent).data));
        if (event.event_type !== type || event.sequence <= after) return;
        after = event.sequence;
        if (type !== "heartbeat") callbacks.event(event);
        if (type === "run.completed" || type === "run.failed") void reconcile();
      } catch { callbacks.error("Không thể đọc tiến trình chấm. Đang khôi phục kết quả đã lưu…"); void reconcile(); }
    });
    connection.onerror = () => { if (!stopped && source === connection) void reconcile(); };
  }
  connect();
  // View cleanup owns only observation, never the backend run or its provider requests.
  return () => { stopped = true; closeSource(); if (timer) clearTimeout(timer); };
}
