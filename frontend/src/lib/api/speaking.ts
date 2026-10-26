import { gradingSchema } from "./grading";
import { focusedUnitSchema } from "./attempts";
import { z } from "zod";
import { apiRequest, apiResponse, type ApiRequester } from "./client";

export const speakingPromptSchema = z.object({
  id: z.string().uuid(), order_index: z.number().int(), prompt_type: z.enum(["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]),
  prompt_text: z.string(), preparation_seconds: z.number().int(), response_seconds: z.number().int(),
  config_json: z.object({ cue_points: z.array(z.string()).optional() }), part_number: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  part_title: z.string().nullable(), instructions: z.string().nullable(),
});
export const speakingStateSchema = z.object({
  attempt_id: z.string().uuid(), mode: z.enum(["PRACTICE", "EXAM"]),
  phase: z.enum(["QUESTION_ENTER", "PREPARING", "STARTING", "RECORDING", "FINALIZING", "COMPLETED", "INTERRUPTED", "RECOVERY_GRACE", "BROWSING"]),
  current_prompt: speakingPromptSchema.nullable(), response_id: z.string().uuid().nullable(), take_number: z.number().int().nullable(),
  phase_started_at: z.string().nullable(), phase_deadline_at: z.string().nullable(), remaining_ms: z.number().nonnegative(), server_time: z.string(),
  can_retry: z.boolean(), can_replay: z.boolean(), scratch_notes: z.string(), interruption_generation: z.number().int(), interruption_count: z.number().int(),
  recovery_state: z.string().nullable(), recovery_grace_used: z.boolean(), last_resumed_at: z.string().nullable(),
  recovery_grace_deadline_at: z.string().nullable().default(null), recovery_grace_seconds: z.literal(7).default(7), recovery_allowed: z.boolean().default(false), next_segment_index: z.number().int().default(0),
  practice_flow: z.enum(["GUIDED", "FREE"]).nullable().optional(), focused_part_number: z.union([z.literal(1), z.literal(2), z.literal(3)]).nullable().optional(),
  navigation: z.array(z.object({ id: z.string().uuid(), order_index: z.number().int().nonnegative(), status: z.enum(["UNANSWERED", "COMMITTED"]), current: z.boolean() })).max(100).optional(),
  can_finish_practice: z.boolean().optional(),
});
export type SpeakingState = z.infer<typeof speakingStateSchema>;
export async function getSpeakingState(id: string, request: ApiRequester = apiRequest) { return speakingStateSchema.parse(await request(`/speaking-attempts/${id}/state`)); }
async function mutate(id: string, action: string, body: unknown, method = "POST") { return speakingStateSchema.parse(await apiRequest(`/speaking-attempts/${id}/${action}`, { method, body: JSON.stringify(body) })); }
export const beginSpeaking = (id: string, prompt_id: string) => mutate(id, "begin", { prompt_id });
export const skipSpeakingPreparation = (id: string, prompt_id: string, take_number: number) => mutate(id, "skip-preparation", { prompt_id, take_number });
export const selectSpeakingPrompt = (id: string, prompt_id: string) => mutate(id, "select-prompt", { prompt_id });
export const finishSpeakingPractice = (id: string) => mutate(id, "finish-practice", {});
export const heartbeatSpeaking = (id: string, prompt_id: string, take_number: number) => mutate(id, "heartbeat", { prompt_id, take_number });
export const finishSpeaking = (id: string, prompt_id: string, take_number: number, completion_reason: "USER_DONE" | "TIMEOUT") => mutate(id, "finish", { prompt_id, take_number, completion_reason });
export const retrySpeaking = (id: string, prompt_id: string, take_number: number) => mutate(id, "retry", { prompt_id, take_number });
export const saveSpeakingNotes = (id: string, prompt_id: string, scratch_notes: string) => mutate(id, "notes", { prompt_id, scratch_notes }, "PUT");
export const interruptSpeaking = (id: string, prompt_id: string, take_number: number, interruption_generation: number) => mutate(id, "interrupt", { prompt_id, take_number, interruption_generation });
export const resumeSpeaking = (id: string, prompt_id: string, take_number: number, interruption_generation: number) => mutate(id, "resume", { prompt_id, take_number, interruption_generation });
const chunkSchema = z.object({ id: z.string().uuid(), sequence: z.number().int(), sha256: z.string(), byte_size: z.number().int() });
export const segmentSchema = z.object({ id: z.string().uuid(), segment_index: z.number().int(), mime_type: z.string(), chunk_count: z.number().int().nullable(), closed_at: z.string().nullable(), chunks: z.array(chunkSchema).default([]), content_url: z.string().nullable().default(null) });
const responseSchema = z.object({ id: z.string().uuid(), prompt_id: z.string().uuid(), active_take_number: z.number().int(), started_at: z.string(), completed_at: z.string().nullable(), duration_ms: z.number().int(), status: z.string(), completion_reason: z.string().nullable(), locked: z.boolean(), committed_audio_fingerprint: z.string().nullable() });
export const manifestSchema = z.object({ response: responseSchema, segments: z.array(segmentSchema) });
export type SpeakingManifest = z.infer<typeof manifestSchema>;
export async function openSpeakingSegment(id: string, prompt_id: string, take_number: number, segment_index: number, mime_type: string) { return segmentSchema.parse(await apiRequest(`/speaking-attempts/${id}/segments`, { method: "POST", body: JSON.stringify({ prompt_id, take_number, segment_index, mime_type }) })); }
export async function uploadSpeakingChunk(id: string, segment: string, sequence: number, blob: Blob) { return chunkSchema.parse(await apiRequest(`/speaking-attempts/${id}/segments/${segment}/chunks/${sequence}`, { method: "PUT", headers: { "Content-Type": blob.type || "application/octet-stream" }, body: blob })); }
export async function closeSpeakingSegment(id: string, segment: string, chunk_count: number) { return segmentSchema.parse(await apiRequest(`/speaking-attempts/${id}/segments/${segment}/close`, { method: "POST", body: JSON.stringify({ chunk_count }) })); }
export async function getSpeakingManifest(id: string, response: string) { return manifestSchema.parse(await apiRequest(`/speaking-attempts/${id}/responses/${response}/manifest`)); }
export async function fetchSpeakingAudio(path: string) { if (!/^\/speaking-attempts\/[^/]+\/segments\/[^/]+\/content$/.test(path)) throw new Error("SPEAKING_MEDIA_INVALID"); return (await apiResponse(path)).blob(); }
const finalBandSchema = z.number().min(0).max(9).multipleOf(0.5);
export const speakingFinalScoreSchema = z.object({
  fc: finalBandSchema, lr: finalBandSchema, gra: finalBandSchema, pr: finalBandSchema, overall_band: finalBandSchema,
  fc_feedback: z.string().nullable().optional(), lr_feedback: z.string().nullable().optional(),
  gra_feedback: z.string().nullable().optional(), pr_feedback: z.string().nullable().optional(),
});
export type SpeakingCriteriaInput = Omit<z.infer<typeof speakingFinalScoreSchema>, "overall_band">;
export const speakingReviewSchema = z.object({ grading: gradingSchema.optional(), final_score: speakingFinalScoreSchema.nullable().optional(), focused_unit: focusedUnitSchema.nullable().optional(), practice_flow: z.enum(["GUIDED", "FREE"]).nullable().optional(), attempt_id: z.string().uuid(), test_title: z.string(), can_generate_transcript: z.boolean().default(true), parts: z.array(z.object({ part_number: z.number().int(), responses: z.array(manifestSchema.extend({ prompt: speakingPromptSchema })), unanswered_prompts: z.array(speakingPromptSchema).optional() })) });
export type SpeakingReviewData = z.infer<typeof speakingReviewSchema>;
export async function getSpeakingReview(id: string, request: ApiRequester = apiRequest) { return speakingReviewSchema.parse(await request(`/speaking-attempts/${id}/review`)); }

export async function saveSpeakingFinalScore(id: string, scores: SpeakingCriteriaInput) {
  return speakingReviewSchema.parse(await apiRequest(`/speaking-attempts/${id}/final-score`, { method: "PUT", body: JSON.stringify(scores) }));
}
