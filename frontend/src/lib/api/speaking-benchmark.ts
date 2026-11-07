import { z } from "zod";
import { API_BASE_URL, apiRequest, type ApiRequester } from "./client";

const root = "/admin/speaking-benchmark";
const band = z.number().min(0).max(9).multipleOf(0.5).nullable();
export const speakingBandsSchema = z.object({ fc: band, lr: band, gra: band, pr: band, overall: band }).strict();
export const speakingMetadataSchema = z.object({ code: z.string().min(1).max(80), candidate_id: z.string().max(120), split: z.enum(["DEV", "HOLDOUT"]), source_note: z.string().min(1).max(2000), rights_confirmed: z.literal(true) }).strict();
export const speakingSampleSchema = speakingMetadataSchema.extend({ id: z.string().uuid(), source_sha256: z.string().regex(/^[a-f0-9]{64}$/), mime_type: z.enum(["audio/mpeg", "audio/wav"]), byte_size: z.number().int().positive(), duration_ms: z.number().int().positive(), status: z.enum(["DRAFT", "PROCESSING", "REVIEW", "APPROVED"]), revision: z.number().int(), review_revision: z.number().int(), label_revision: z.number().int(), label_status: z.enum(["UNLABELLED", "UNVERIFIED", "HUMAN_VERIFIED"]), approved_fingerprint: z.string().nullable(), created_at: z.string(), updated_at: z.string() }).strict();
export const speakingJobSchema = z.object({ id: z.string().uuid(), status: z.enum(["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]), stage: z.string(), progress: z.number().int().min(0).max(100), attempts: z.number().int(), error_code: z.string().nullable(), created_at: z.string(), started_at: z.string().nullable(), finished_at: z.string().nullable() }).strict();
export const speakerTurnSchema = z.object({ id: z.string(), speaker_id: z.string(), start_ms: z.number().int(), end_ms: z.number().int() }).strict();
export const speakingSegmentSchema = z.object({ id: z.string().min(1).max(100), speaker_id: z.string(), start_ms: z.number().int().nonnegative(), end_ms: z.number().int().positive(), included: z.boolean(), prompt_text: z.string().max(10000), cue_points: z.array(z.string().min(1).max(1000)).max(20), prompt_verified: z.boolean(), long_turn: z.boolean(), silence_reviewed: z.boolean() }).strict().refine(s => s.end_ms > s.start_ms, "Invalid response window");
export const speakingDraftSchema = z.object({ schema_version: z.literal(1), source_sha256: z.string(), model_fingerprint: z.string(), roles: z.record(z.string(), z.enum(["candidate", "examiner", "other", "unknown"])), candidate_speaker_id: z.string().nullable(), candidate_confirmed: z.boolean(), part2_start_ms: z.number().int().positive().nullable(), part3_start_ms: z.number().int().positive().nullable(), boundaries_verified: z.boolean(), segments: z.array(speakingSegmentSchema).max(100) }).strict();
const diarizationSchema = z.object({ schema_version: z.literal(1), source: z.string(), source_sha256: z.string(), duration_ms: z.number(), cache_key: z.string(), identity: z.record(z.string(), z.unknown()), regular: z.array(speakerTurnSchema).max(20000), exclusive: z.array(speakerTurnSchema).max(20000), latency_ms: z.number().nullable(), limitations: z.array(z.string()) }).strict();
export const speakingReviewSchema = z.object({ revision: z.number().int(), draft: speakingDraftSchema, diarization: diarizationSchema, approved_at: z.string().nullable(), manifest: z.object({ schema_version: z.literal(1), candidate_only_verified: z.boolean(), segments: z.array(z.unknown()).max(100) }).passthrough().nullable(), approval_errors: z.array(z.string()), role_suggestions: z.record(z.string(), z.enum(["candidate", "examiner", "unknown"])) }).strict();
export const speakingLabelsSchema = z.object({ revision: z.number().int().nonnegative(), bands: speakingBandsSchema, provenance: z.enum(["human_examiner", "published_human_assessment", "unverified"]), reference: z.string().max(2000), verified: z.boolean(), examiner: z.string().max(500), notes: z.string().max(5000) }).strict().refine(v => !v.verified || (v.provenance !== "unverified" && v.reference.trim().length > 0), "Independent human provenance is required");
export const speakingAvailabilitySchema = z.object({ execution: z.enum(["local", "remote", "disabled"]), can_queue: z.boolean(), reason: z.string().nullable(), max_bytes: z.number(), max_duration_ms: z.number() }).strict();
const pageSchema = z.object({ items: z.array(speakingSampleSchema).max(50), total: z.number().int(), offset: z.number().int(), limit: z.number().int() }).strict();

export type SpeakingSample = z.infer<typeof speakingSampleSchema>;
export type SpeakingMetadata = z.infer<typeof speakingMetadataSchema>;
export type SpeakingJob = z.infer<typeof speakingJobSchema>;
export type SpeakingReview = z.infer<typeof speakingReviewSchema>;
export type SpeakingDraft = z.infer<typeof speakingDraftSchema>;
export type SpeakingSegment = z.infer<typeof speakingSegmentSchema>;
export type SpeakingLabels = z.infer<typeof speakingLabelsSchema>;
export type SpeakerTurn = z.infer<typeof speakerTurnSchema>;
export type SpeakingAvailability = z.infer<typeof speakingAvailabilitySchema>;

const path = (id: string) => `${root}/samples/${encodeURIComponent(id)}`;
export function speakingAudioUrl(id: string) { return `${API_BASE_URL}${path(id)}/audio`; }
export async function speakingAvailability(request: ApiRequester = apiRequest) { return speakingAvailabilitySchema.parse(await request(`${root}/availability`)); }
export async function listSpeakingSamples(offset = 0, request: ApiRequester = apiRequest) { return pageSchema.parse(await request(`${root}/samples?offset=${offset}&limit=25`)); }
export async function getSpeakingSample(id: string, request: ApiRequester = apiRequest) { return speakingSampleSchema.parse(await request(path(id))); }
export async function uploadSpeakingSample(file: File, metadata: SpeakingMetadata, request: ApiRequester = apiRequest) {
  const body = new FormData(); body.set("metadata", JSON.stringify(speakingMetadataSchema.parse(metadata))); body.set("file", file);
  return speakingSampleSchema.parse(await request(`${root}/samples`, { method: "POST", body }));
}
export async function patchSpeakingSample(id: string, value: SpeakingMetadata, revision: number, request: ApiRequester = apiRequest) { return speakingSampleSchema.parse(await request(path(id), { method: "PATCH", body: JSON.stringify({ ...speakingMetadataSchema.parse(value), expected_revision: revision }) })); }
export async function deleteSpeakingSample(id: string, revision: number, request: ApiRequester = apiRequest) { await request(`${path(id)}?expected_revision=${revision}`, { method: "DELETE" }); }
export async function queueSpeakingDiarization(id: string, request: ApiRequester = apiRequest) { return speakingJobSchema.parse(await request(`${path(id)}/diarize`, { method: "POST" })); }
export async function getSpeakingJobs(id: string, request: ApiRequester = apiRequest) { return z.array(speakingJobSchema).max(20).parse(await request(`${path(id)}/jobs`)); }
export async function cancelSpeakingJob(id: string, jobId: string, request: ApiRequester = apiRequest) { return speakingJobSchema.parse(await request(`${path(id)}/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" })); }
export async function getSpeakingReview(id: string, revision?: number, request: ApiRequester = apiRequest) { return speakingReviewSchema.parse(await request(`${path(id)}/review${revision ? `?revision=${revision}` : ""}`)); }
export async function saveSpeakingReview(id: string, draft: SpeakingDraft, revision: number, request: ApiRequester = apiRequest) { return speakingReviewSchema.parse(await request(`${path(id)}/review`, { method: "PATCH", body: JSON.stringify({ expected_revision: revision, draft: speakingDraftSchema.parse(draft) }) })); }
export async function suggestSpeakingWindows(id: string, draft: SpeakingDraft, revision: number, request: ApiRequester = apiRequest) { return speakingDraftSchema.parse(await request(`${path(id)}/review/suggest`, { method: "POST", body: JSON.stringify({ expected_revision: revision, draft: speakingDraftSchema.parse(draft) }) })); }
export async function approveSpeakingReview(id: string, revision: number, request: ApiRequester = apiRequest) { return speakingReviewSchema.parse(await request(`${path(id)}/approve`, { method: "POST", body: JSON.stringify({ expected_revision: revision }) })); }
export async function getSpeakingLabels(id: string, request: ApiRequester = apiRequest) { return speakingLabelsSchema.parse(await request(`${path(id)}/human-labels`)); }
export async function saveSpeakingLabels(id: string, value: SpeakingLabels, request: ApiRequester = apiRequest) {
  const { revision, ...labels } = speakingLabelsSchema.parse(value);
  return speakingLabelsSchema.parse(await request(`${path(id)}/human-labels`, { method: "PUT", body: JSON.stringify({ expected_revision: revision, ...labels }) }));
}
