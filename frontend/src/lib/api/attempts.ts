import { z } from "zod";
import { apiRequest } from "./client";

export type TimerMode = "COUNTDOWN" | "COUNT_UP";

export const attemptResponseSchema = z.object({
  attempt_id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  test_session_id: z.string().uuid().nullable().optional(),
  attempt_context: z.enum(["STANDALONE", "FULL_MOCK"]).optional(),
  module: z.enum(["READING", "LISTENING", "WRITING"]),
  status: z.enum(["IN_PROGRESS", "PAUSED", "SUBMITTED", "AUTO_SUBMITTED", "INTERRUPTED", "ABANDONED"]),
  finished_reason: z.string().nullable(),
  timer_mode: z.enum(["COUNTDOWN", "COUNT_UP"]),
  timer_limit_seconds: z.number().nullable(),
  started_at: z.string(),
  paused_at: z.string().nullable(),
  total_paused_seconds: z.number().int().nonnegative(),
  deadline_at: z.string().nullable(),
  last_active_at: z.string(),
  finished_at: z.string().nullable(),
  elapsed_seconds: z.number(),
  remaining_seconds: z.number().nullable(),
  raw_score: z.number().nullable(),
  max_score: z.number().nullable(),
  band_score: z.number().nullable(),
  server_time: z.string(),
});

const writingResponseSchema = z.object({
  writing_task_id: z.string().uuid(),
  content: z.string(),
  word_count: z.number().int().nonnegative(),
  saved_at: z.string(),
});

export type AttemptResponse = z.infer<typeof attemptResponseSchema>;
export type WritingResponse = z.infer<typeof writingResponseSchema>;

export async function startAttempt(input: {
  test_version_id: string;
  module: "READING" | "LISTENING" | "WRITING";
  timer: { mode: TimerMode; duration_seconds?: number };
}) {
  return attemptResponseSchema.parse(await apiRequest<unknown>("/attempts", {
    method: "POST",
    body: JSON.stringify(input),
  }));
}

export function saveAnswer(attemptId: string, questionId: string, value: unknown) {
  return apiRequest(`/attempts/${attemptId}/answers/${questionId}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function recordActivity(attemptId: string) {
  return apiRequest(`/attempts/${attemptId}/activity`, {
    method: "POST",
    body: JSON.stringify({ client_observed_at: new Date().toISOString() }),
  });
}

export function recordNavigation(
  attemptId: string,
  kind: "PASSAGE" | "LISTENING_PART" | "WRITING_TASK" | "QUESTION",
  targetId: string,
) {
  return apiRequest(`/attempts/${attemptId}/navigation`, {
    method: "POST",
    body: JSON.stringify({ kind, target_id: targetId }),
  });
}

export async function saveWritingResponse(
  attemptId: string,
  writingTaskId: string,
  content: string,
): Promise<WritingResponse> {
  return writingResponseSchema.parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/writing/${writingTaskId}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  );
}

export async function deleteAttempt(attemptId: string): Promise<void> {
  await apiRequest(`/attempts/${attemptId}`, { method: "DELETE" });
}

export async function pauseAttempt(attemptId: string): Promise<AttemptResponse> {
  return attemptResponseSchema.parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/pause`, { method: "POST" }),
  );
}

export async function resumeAttempt(attemptId: string): Promise<AttemptResponse> {
  return attemptResponseSchema.parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/resume`, { method: "POST" }),
  );
}
