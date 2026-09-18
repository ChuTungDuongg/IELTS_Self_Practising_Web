import { z } from "zod";
import { apiRequest } from "./client";

const attemptSchema = z.object({
  attempt_id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  module: z.string(),
  status: z.string(),
  finished_reason: z.string().nullable(),
  timer_mode: z.enum(["COUNTDOWN", "COUNT_UP"]),
  timer_limit_seconds: z.number().nullable(),
  started_at: z.string(),
  deadline_at: z.string().nullable(),
  last_active_at: z.string(),
  finished_at: z.string().nullable(),
  elapsed_seconds: z.number(),
  remaining_seconds: z.number().nullable(),
  raw_score: z.number().nullable(),
  max_score: z.number().nullable(),
  server_time: z.string(),
});

const questionSchema = z.object({
  id: z.string().uuid(), number: z.number(), prompt: z.string(),
  config: z.record(z.string(), z.unknown()), order_index: z.number(),
  value: z.unknown().nullable().optional(), flagged: z.boolean(),
});
const groupSchema = z.object({
  id: z.string().uuid(), question_type: z.string(), instruction: z.string(),
  config: z.record(z.string(), z.unknown()), order_index: z.number(),
  questions: z.array(questionSchema),
});
const passageSchema = z.object({
  id: z.string().uuid(), title: z.string(), order_index: z.number(),
  blocks: z.array(z.object({ id: z.string().uuid(), type: z.enum(["paragraph", "heading"]), text: z.string() })),
  question_groups: z.array(groupSchema),
});
const highlightSchema = z.object({
  id: z.string().uuid(), passage_id: z.string().uuid(), start_block_id: z.string().uuid(),
  start_offset: z.number(), end_block_id: z.string().uuid(), end_offset: z.number(),
  selected_text: z.string(), created_at: z.string(),
});
const examSchema = z.object({ attempt: attemptSchema, test_title: z.string(), passages: z.array(passageSchema), highlights: z.array(highlightSchema) });
export type ExamPayload = z.infer<typeof examSchema>;
export type ExamPassage = z.infer<typeof passageSchema>;
export type Highlight = z.infer<typeof highlightSchema>;

export async function getExam(attemptId: string): Promise<ExamPayload> {
  return examSchema.parse(await apiRequest<unknown>(`/attempts/${attemptId}/exam`));
}

export function submitAttempt(attemptId: string) {
  return apiRequest(`/attempts/${attemptId}/submit`, { method: "POST" });
}

export function saveFlag(attemptId: string, questionId: string, flagged: boolean) {
  return apiRequest(`/attempts/${attemptId}/flags/${questionId}`, { method: "PUT", body: JSON.stringify({ flagged }) });
}

export async function createHighlight(attemptId: string, body: Omit<Highlight, "id" | "created_at">) {
  return highlightSchema.parse(await apiRequest<unknown>(`/attempts/${attemptId}/highlights`, { method: "POST", body: JSON.stringify(body) }));
}

export function deleteHighlight(attemptId: string, highlightId: string) {
  return apiRequest(`/attempts/${attemptId}/highlights/${highlightId}`, { method: "DELETE" });
}

export async function getReadingReview(attemptId: string) {
  return apiRequest<{
    review: {
      attempt: z.infer<typeof attemptSchema>;
      test_title: string;
      answers: Array<{ question_id: string; question_number: number; prompt: string; value: unknown; answer_key: Record<string, unknown>; is_correct: boolean | null; explanation: string | null }>;
    };
    passages: Array<{
      id: string; title: string; order_index: number;
      blocks: Array<{ id: string; type: "paragraph" | "heading"; text: string }>;
      question_groups: Array<{
        id: string; question_type: string; instruction: string; config: Record<string, unknown>; order_index: number;
        questions: Array<{ id: string; number: number; prompt: string; config: Record<string, unknown>; answer_key: Record<string, unknown>; explanation: string | null; order_index: number }>;
      }>;
    }>;
  }>(`/attempts/${attemptId}/reading-review`);
}
