import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";

export const speakingPromptSchema = z.object({
  id: z.string().uuid(), order_index: z.number().int(), prompt_type: z.enum(["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]),
  prompt_text: z.string(), preparation_seconds: z.number().int(), response_seconds: z.number().int(),
  config_json: z.object({ cue_points: z.array(z.string()).optional() }), part_number: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  part_title: z.string().nullable(), instructions: z.string().nullable(),
});
export const speakingStateSchema = z.object({
  attempt_id: z.string().uuid(), mode: z.enum(["PRACTICE", "EXAM"]),
  phase: z.enum(["QUESTION_ENTER", "PREPARING", "STARTING", "RECORDING", "FINALIZING", "COMPLETED", "INTERRUPTED", "RECOVERY_GRACE"]),
  current_prompt: speakingPromptSchema.nullable(), response_id: z.string().uuid().nullable(), take_number: z.number().int().nullable(),
  phase_started_at: z.string().nullable(), phase_deadline_at: z.string().nullable(), remaining_ms: z.number().nonnegative(), server_time: z.string(),
  can_retry: z.boolean(), can_replay: z.boolean(), scratch_notes: z.string(), interruption_generation: z.number().int(), interruption_count: z.number().int(),
  recovery_state: z.string().nullable(), recovery_grace_used: z.boolean(), last_resumed_at: z.string().nullable(),
});
export type SpeakingState = z.infer<typeof speakingStateSchema>;
export async function getSpeakingState(id: string, request: ApiRequester = apiRequest) { return speakingStateSchema.parse(await request(`/speaking-attempts/${id}/state`)); }
async function mutate(id: string, action: string, body: unknown, method = "POST") { return speakingStateSchema.parse(await apiRequest(`/speaking-attempts/${id}/${action}`, { method, body: JSON.stringify(body) })); }
export const beginSpeaking = (id: string, prompt_id: string) => mutate(id, "begin", { prompt_id });
export const heartbeatSpeaking = (id: string, prompt_id: string, take_number: number) => mutate(id, "heartbeat", { prompt_id, take_number });
export const finishSpeaking = (id: string, prompt_id: string, take_number: number, completion_reason: "USER_DONE" | "TIMEOUT") => mutate(id, "finish", { prompt_id, take_number, completion_reason });
export const retrySpeaking = (id: string, prompt_id: string, take_number: number) => mutate(id, "retry", { prompt_id, take_number });
export const saveSpeakingNotes = (id: string, prompt_id: string, scratch_notes: string) => mutate(id, "notes", { prompt_id, scratch_notes }, "PUT");
