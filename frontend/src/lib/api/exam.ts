import { z } from "zod";
import { attemptResponseSchema } from "./attempts";
import { apiRequest } from "./client";

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
  blocks: z.array(z.object({ id: z.string().uuid(), type: z.enum(["paragraph", "heading"]), label: z.string().nullable().optional(), text: z.string() })),
  question_groups: z.array(groupSchema),
});
const assetSchema = z.object({ id: z.string().uuid(), original_name: z.string(), mime_type: z.string(), file_size: z.number(), content_url: z.string() });
const listeningPartSchema = z.object({ id: z.string().uuid(), title: z.string(), order_index: z.number(), question_groups: z.array(groupSchema) });
const writingTaskSchema = z.object({
  id: z.string().uuid(),
  task_number: z.number().int(),
  prompt: z.string(),
  image_asset_id: z.string().uuid().nullable().default(null),
  image_asset: assetSchema.nullable().default(null),
  minimum_recommended_words: z.number().int().nullable(),
  recommended_duration_seconds: z.number().int().nullable(),
  order_index: z.number().int(),
  content: z.string(),
  word_count: z.number().int().nonnegative(),
});
const highlightSchema = z.object({
  id: z.string().uuid(), target_kind: z.enum(["PASSAGE_BLOCK", "QUESTION_PROMPT", "TEXT_COMPLETION_SEGMENT"]), target_id: z.string().uuid(), segment_id: z.string().uuid().nullable().optional(),
  passage_id: z.string().uuid().nullable().optional(), start_block_id: z.string().uuid().nullable().optional(),
  start_offset: z.number(), end_block_id: z.string().uuid().nullable().optional(), end_offset: z.number(),
  selected_text: z.string(), created_at: z.string(),
});
const examSchema = z.object({ attempt: attemptResponseSchema, test_title: z.string(), passages: z.array(passageSchema), highlights: z.array(highlightSchema), listening_audio_asset: assetSchema.nullable().default(null), listening_parts: z.array(listeningPartSchema).default([]), writing_tasks: z.array(writingTaskSchema).default([]) });
export type ExamPayload = z.infer<typeof examSchema>;
export type ExamPassage = z.infer<typeof passageSchema>;
export type ExamListeningPart = z.infer<typeof listeningPartSchema>;
export type ExamWritingTask = z.infer<typeof writingTaskSchema>;
export type Highlight = z.infer<typeof highlightSchema>;
export type HighlightTarget = Pick<Highlight, "target_kind" | "target_id" | "segment_id">;
export type HighlightCreate = HighlightTarget & Pick<Highlight, "start_offset" | "end_offset" | "selected_text">;

export async function getExam(attemptId: string): Promise<ExamPayload> {
  return examSchema.parse(await apiRequest<unknown>(`/attempts/${attemptId}/exam`));
}

export function submitAttempt(attemptId: string) {
  return apiRequest(`/attempts/${attemptId}/submit`, { method: "POST" });
}

export function saveFlag(attemptId: string, questionId: string, flagged: boolean) {
  return apiRequest(`/attempts/${attemptId}/flags/${questionId}`, { method: "PUT", body: JSON.stringify({ flagged }) });
}

export async function createHighlight(attemptId: string, body: HighlightCreate) {
  return highlightSchema.parse(await apiRequest<unknown>(`/attempts/${attemptId}/highlights`, { method: "POST", body: JSON.stringify(body) }));
}

export function deleteHighlight(attemptId: string, highlightId: string) {
  return apiRequest(`/attempts/${attemptId}/highlights/${highlightId}`, { method: "DELETE" });
}

export function deleteAllHighlights(attemptId: string) {
  return apiRequest(`/attempts/${attemptId}/highlights`, { method: "DELETE" });
}

export async function getReadingReview(attemptId: string) {
  return apiRequest<{
    review: {
      attempt: z.infer<typeof attemptResponseSchema>;
      test_title: string;
      answers: Array<{ question_id: string; question_number: number; prompt: string; value: unknown; answer_key: Record<string, unknown>; is_correct: boolean | null; explanation: string | null }>;
    };
    highlights: z.infer<typeof highlightSchema>[];
    passages: Array<{
      id: string; title: string; order_index: number;
      blocks: Array<{ id: string; type: "paragraph" | "heading"; label?: string | null; text: string }>;
      question_groups: Array<{
        id: string; question_type: string; instruction: string; config: Record<string, unknown>; order_index: number;
        questions: Array<{ id: string; number: number; prompt: string; config: Record<string, unknown>; answer_key: Record<string, unknown>; explanation: string | null; order_index: number }>;
      }>;
    }>;
  }>(`/attempts/${attemptId}/reading-review`);
}

export async function getListeningReview(attemptId: string) {
  return apiRequest<{
    review: { attempt: z.infer<typeof attemptResponseSchema>; test_title: string; answers: Array<{ question_id: string; question_number: number; prompt: string; value: unknown; answer_key: Record<string, unknown>; is_correct: boolean | null; explanation: string | null }> };
    audio_asset: z.infer<typeof assetSchema> | null;
    parts: Array<{ id: string; title: string; order_index: number; question_groups: Array<{ id: string; question_type: string; instruction: string; config: Record<string, unknown>; image_asset?: z.infer<typeof assetSchema> | null; order_index: number; questions: Array<{ id: string; number: number; prompt: string; config: Record<string, unknown>; answer_key: Record<string, unknown>; explanation: string | null; order_index: number }> }> }>;
  }>(`/attempts/${attemptId}/listening-review`);
}

const writingReviewTaskSchema = z.object({
  writing_task_id: z.string().uuid(),
  task_number: z.number().int(),
  prompt: z.string(),
  image_asset_id: z.string().uuid().nullable().default(null),
  image_asset: assetSchema.nullable().default(null),
  minimum_recommended_words: z.number().int().nullable(),
  recommended_duration_seconds: z.number().int().nullable(),
  content: z.string(),
  word_count: z.number().int().nonnegative(),
  score: z.object({
    ta: z.number(),
    cc: z.number(),
    lr: z.number(),
    gra: z.number(),
    overall: z.number(),
  }).nullable().default(null),
});

const writingReviewSchema = z.object({
  review: z.object({
    attempt: attemptResponseSchema,
    test_title: z.string(),
    answers: z.array(z.unknown()),
    writing_responses: z.array(writingReviewTaskSchema).default([]),
    highlights: z.array(z.unknown()).default([]),
    flags: z.array(z.unknown()).default([]),
  }),
  tasks: z.array(writingReviewTaskSchema),
  task1_overall: z.number().nullable(),
  task2_overall: z.number().nullable(),
  weighted_overall: z.number().nullable(),
  band_score: z.number().nullable(),
});

export type WritingReviewPayload = z.infer<typeof writingReviewSchema>;

export async function getWritingReview(attemptId: string): Promise<WritingReviewPayload> {
  return writingReviewSchema.parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/writing-review`),
  );
}

export type WritingCriteriaInput = { ta: number; cc: number; lr: number; gra: number };

export async function saveWritingTaskScore(
  attemptId: string,
  writingTaskId: string,
  scores: WritingCriteriaInput,
): Promise<WritingReviewPayload> {
  return writingReviewSchema.parse(
    await apiRequest<unknown>(`/attempts/${attemptId}/writing-scores/${writingTaskId}`, {
      method: "PUT",
      body: JSON.stringify(scores),
    }),
  );
}
