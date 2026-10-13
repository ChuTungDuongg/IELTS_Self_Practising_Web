import { gradingSchema } from "./grading";
import type { WritingCriteriaInput } from "./exam";
import type { SpeakingCriteriaInput } from "./speaking";
import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";
import { attemptResponseSchema } from "./attempts";
import { aiRunSchema } from "./writing-ai";
import { appendPageQuery, type PageOptions } from "./pagination";
import { readingReviewSchema, listeningReviewSchema, writingReviewSchema, writingReviewTaskSchema } from "./exam";
import { speakingReviewSchema } from "./speaking";
import { speakingAIRunSchema } from "./speaking-ai";
const summarySchema = z.object({
  student_id: z.string().uuid(),
  student_display_name: z.string(),
  attempt: attemptResponseSchema,
  session_id: z.string().uuid().nullable()
});
export type AssignmentResultSummary = z.infer<typeof summarySchema>;
const detailSchema = summarySchema.extend({
  grading: gradingSchema.optional(),
  reading_review: readingReviewSchema.nullable(),
  listening_review: listeningReviewSchema.nullable(),
  writing_review: writingReviewSchema.nullable(),
  speaking_review: speakingReviewSchema.nullable().optional(),
  speaking_ai_run: speakingAIRunSchema.nullable().optional(),
  ai_runs: z.array(aiRunSchema),
  submitted_answers: z.array(z.object({
    question_id: z.string().uuid(),
    value: z.unknown(),
    is_correct: z.boolean().nullable()
  })),
  writing_responses: z.array(writingReviewTaskSchema),
});
export type AssignmentResultDetail = z.infer<typeof detailSchema>;
const base = (classroomId: string, assignmentId: string) => `/classrooms/${encodeURIComponent(classroomId)}/assignments/${encodeURIComponent(assignmentId)}`;
export async function listAssignmentResults(classroomId: string, assignmentId: string, request: ApiRequester = apiRequest, options?: PageOptions): Promise<AssignmentResultSummary[]> {
  return z.array(summarySchema).parse(await request<unknown>(appendPageQuery(`${base(classroomId, assignmentId)}/results`, options)));
}
export async function getAssignmentResult(classroomId: string, assignmentId: string, attemptId: string, request: ApiRequester = apiRequest): Promise<AssignmentResultDetail> {
  return detailSchema.parse(await request<unknown>(`${base(classroomId, assignmentId)}/attempts/${encodeURIComponent(attemptId)}`));
}

export async function saveAssignmentWritingScore(classroomId: string, assignmentId: string, attemptId: string, taskId: string, scores: WritingCriteriaInput) {
  return writingReviewSchema.parse(await apiRequest(`${base(classroomId, assignmentId)}/attempts/${encodeURIComponent(attemptId)}/writing-scores/${encodeURIComponent(taskId)}`, { method: "PUT", body: JSON.stringify(scores) }));
}
export async function saveAssignmentSpeakingScore(classroomId: string, assignmentId: string, attemptId: string, scores: SpeakingCriteriaInput) {
  return speakingReviewSchema.parse(await apiRequest(`${base(classroomId, assignmentId)}/attempts/${encodeURIComponent(attemptId)}/speaking-score`, { method: "PUT", body: JSON.stringify(scores) }));
}
