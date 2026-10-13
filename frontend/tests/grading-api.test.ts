import { beforeEach, expect, it, vi } from "vitest";
import { apiRequest } from "@/lib/api/client";
import { getAssignmentResult, saveAssignmentSpeakingScore, saveAssignmentWritingScore } from "@/lib/api/classroom-results";
import { saveSpeakingFinalScore, speakingFinalScoreSchema, speakingReviewSchema } from "@/lib/api/speaking";
import { writingReviewSchema } from "@/lib/api/exam";
vi.mock("@/lib/api/client", async original => ({ ...await original<typeof import("@/lib/api/client")>(), apiRequest: vi.fn() }));
const id = "11111111-1111-4111-8111-111111111111";
const grading = { context: "CLASSROOM", can_edit_final: true, can_copy_ai_to_final: true, waiting_for_teacher: false };
const scores = { fc: 7, lr: 6.5, gra: 6.5, pr: 6.5, fc_feedback: "Fictional feedback" };
const speaking = { attempt_id: id, test_title: "Fictional review", can_generate_transcript: false, parts: [], grading, final_score: { ...scores, overall_band: 6.5 } };
const attempt = { attempt_id: id, test_version_id: id, module: "WRITING", status: "SUBMITTED", finished_reason: "USER_SUBMIT", timer_mode: "COUNT_UP", timer_limit_seconds: null, started_at: "now", paused_at: null, total_paused_seconds: 0, deadline_at: null, last_active_at: "now", finished_at: "now", elapsed_seconds: 5, remaining_seconds: null, raw_score: null, max_score: null, band_score: null, server_time: "now" };
const writing = { grading, review: { attempt, test_title: "Fictional Writing", answers: [] }, tasks: [], task1_overall: null, task2_overall: null, weighted_overall: null, band_score: null };
beforeEach(() => vi.clearAllMocks());
it("uses distinct explicit personal and classroom Speaking final PUT routes and preserves capability/final score", async () => {
  vi.mocked(apiRequest).mockResolvedValue(speaking);
  expect((await saveSpeakingFinalScore(id, scores)).final_score?.fc).toBe(7);
  expect(apiRequest).toHaveBeenLastCalledWith(`/speaking-attempts/${id}/final-score`, { method: "PUT", body: JSON.stringify(scores) });
  expect((await saveAssignmentSpeakingScore(id, id, id, scores)).grading).toEqual(grading);
  expect(apiRequest).toHaveBeenLastCalledWith(`/classrooms/${id}/assignments/${id}/attempts/${id}/speaking-score`, { method: "PUT", body: JSON.stringify(scores) });
});
it("uses the exact assignment scope for Writing PUT", async () => {
  vi.mocked(apiRequest).mockResolvedValue(writing); const input = { ta: 7, cc: 7, lr: 7, gra: 7 };
  expect((await saveAssignmentWritingScore(id, id, id, id, input)).grading).toEqual(grading);
  expect(apiRequest).toHaveBeenLastCalledWith(`/classrooms/${id}/assignments/${id}/attempts/${id}/writing-scores/${id}`, { method: "PUT", body: JSON.stringify(input) });
});
it("preserves classroom detail capability and defaults missing review capabilities to no authority", async () => {
  const detail = await getAssignmentResult(id, id, id, vi.fn().mockResolvedValue({ student_id: id, student_display_name: "Fictional student", attempt, session_id: null, reading_review: null, listening_review: null, writing_review: writing, speaking_review: speaking, ai_runs: [], submitted_answers: [], writing_responses: [], grading }));
  expect(detail.grading).toEqual(grading); expect(detail.speaking_review?.final_score?.overall_band).toBe(6.5);
  expect(speakingReviewSchema.parse({ ...speaking, grading: undefined }).grading).toBeUndefined();
  expect(writingReviewSchema.parse({ ...writing, grading: undefined }).grading).toBeUndefined();
});
it.each([-0.5, 9.5, 6.25])("rejects invalid final Speaking band %s", value => {
  expect(speakingFinalScoreSchema.safeParse({ ...scores, fc: value, overall_band: 6.5 }).success).toBe(false);
});
