import { z } from "zod";
import { apiRequest, API_BASE_URL } from "./client";

const root = "/admin/speaking-benchmark";
const sample = (id: string) => `${root}/samples/${encodeURIComponent(id)}`;
const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });
const band = z.number().min(0).max(9).multipleOf(.5).nullable();
export const bandsSchema = z.object({ fc: band, lr: band, gra: band, pr: band, overall: band }).strict();
export type HumanBands = z.infer<typeof bandsSchema>;
export const criteria = ["fc", "lr", "gra", "pr", "overall"] as const;
export const commentsSchema = z.object({ fc: z.string(), lr: z.string(), gra: z.string(), pr: z.string(), overall: z.string() });
export const raterSchema = z.object({ id: z.string(), kind: z.enum(["INTERNAL", "EXTERNAL"]), display_name: z.string(), user_id: z.string().nullable(), external_key: z.string().nullable(), created_at: z.string() });
export type HumanRater = z.infer<typeof raterSchema>;
export const assignmentSchema = z.object({ id: z.string(), sample_id: z.string(), rater_id: z.string(), review_revision: z.number(), source_sha256: z.string(), manifest_fingerprint: z.string(), permitted_original_audio: z.boolean(), revision: z.number(), revoked_at: z.string().nullable(), created_at: z.string() });
export type RaterAssignment = z.infer<typeof assignmentSchema>;
export const assessmentSchema = z.object({ id: z.string(), assignment_id: z.string(), sample_id: z.string(), rater_id: z.string(), review_revision: z.number(), source_sha256: z.string(), manifest_fingerprint: z.string(), revision: z.number(), status: z.literal("SUBMITTED"), bands: bandsSchema, comments: commentsSchema, independently_performed: z.boolean(), provenance: z.string(), source_reference: z.string(), eligible: z.boolean(), authored_by: z.string(), submitted_at: z.string() });
export type HumanAssessment = z.infer<typeof assessmentSchema>;
export const adjudicationSchema = z.object({ id: z.string(), sample_id: z.string(), review_revision: z.number(), source_sha256: z.string(), manifest_fingerprint: z.string(), revision: z.number(), assessment_refs: z.array(z.record(z.string(), z.unknown())), bands: bandsSchema, rationale: z.string(), policy_version: z.string(), provenance: z.string(), adjudicator_id: z.string(), adjudicated_at: z.string() });
export type HumanAdjudication = z.infer<typeof adjudicationSchema>;
export const blindAssessmentSchema = z.object({ id: z.string(), sample_id: z.string(), review_revision: z.number(), source_sha256: z.string(), manifest_fingerprint: z.string(), revision: z.number(), duration_ms: z.number(), audio_url: z.string(), questions: z.array(z.object({ id: z.string(), part_number: z.number(), prompt_type: z.string(), prompt_text: z.string(), cue_points: z.array(z.string()), start_ms: z.number().nullable(), end_ms: z.number().nullable() }).strict()), assessments: z.array(assessmentSchema), created_at: z.string() }).strict();
export type BlindAssessment = z.infer<typeof blindAssessmentSchema>;
const page = <T extends z.ZodType>(schema: T) => z.object({ items: z.array(schema), total: z.number(), offset: z.number(), limit: z.number() });
export type AssessmentSubmit = { expected_revision: number; bands: HumanBands; comments: z.infer<typeof commentsSchema>; independently_performed: boolean; provenance: "external_verified_report" | "external_unverified"; source_reference: string };
export async function listRaters(offset = 0) { return page(raterSchema).parse(await apiRequest(`${root}/human-raters?offset=${offset}&limit=25`)); }
export async function createRater(body: { kind: "INTERNAL" | "EXTERNAL"; display_name: string; user_id?: string; external_key?: string }) { return raterSchema.parse(await apiRequest(`${root}/human-raters`, post(body))); }
export async function listAssignments(id: string, offset = 0) { return page(assignmentSchema).parse(await apiRequest(`${sample(id)}/rater-assignments?offset=${offset}&limit=25`)); }
export async function createAssignment(id: string, rater_id: string, review_revision: number) { return assignmentSchema.parse(await apiRequest(`${sample(id)}/rater-assignments`, post({ rater_id, review_revision, permitted_original_audio: true }))); }
export async function revokeAssignment(id: string, row: RaterAssignment) { return assignmentSchema.parse(await apiRequest(`${sample(id)}/rater-assignments/${encodeURIComponent(row.id)}/revoke`, post({ expected_revision: row.revision }))); }
export async function listAssessments(id: string, revision: number, offset = 0) { return page(assessmentSchema).parse(await apiRequest(`${sample(id)}/human-assessments?review_revision=${revision}&offset=${offset}&limit=25`)); }
export async function submitExternalAssessment(id: string, assignment_id: string, body: AssessmentSubmit) { return assessmentSchema.parse(await apiRequest(`${sample(id)}/human-assessments`, post({ ...body, assignment_id }))); }
export async function listAdjudications(id: string, revision: number, offset = 0) { return page(adjudicationSchema).parse(await apiRequest(`${sample(id)}/adjudications?review_revision=${revision}&offset=${offset}&limit=25`)); }
export async function adjudicate(id: string, body: { review_revision: number; expected_revision: number; assessment_ids: string[]; bands: HumanBands; rationale: string; policy_version: "human-adjudication-v1" }) { return adjudicationSchema.parse(await apiRequest(`${sample(id)}/adjudications`, post(body))); }
export const agreementSchema = z.object({ protocol: z.string(), independent_raters: z.number(), independent_samples: z.number(), pairs: z.array(z.object({ left_rater_id: z.string(), right_rater_id: z.string(), matched_samples: z.number(), criteria: z.record(z.string(), z.record(z.string(), z.unknown())) })), limitations: z.array(z.string()) });
export type HumanAgreement = z.infer<typeof agreementSchema>;
export async function humanAgreement(id: string, revision: number) { return agreementSchema.parse(await apiRequest(`${root}/human-assessments/agreement?sample_id=${encodeURIComponent(id)}&review_revision=${revision}`)); }
export async function reviewerAssignments(offset = 0) { return page(assignmentSchema).parse(await apiRequest(`${root}/reviewer-assignments?offset=${offset}&limit=25`)); }
export async function blindAssignment(id: string) { return blindAssessmentSchema.parse(await apiRequest(`${root}/reviewer-assignments/${encodeURIComponent(id)}`)); }
export async function submitBlindAssessment(id: string, body: AssessmentSubmit) { return assessmentSchema.parse(await apiRequest(`${root}/reviewer-assignments/${encodeURIComponent(id)}/assessments`, post(body))); }
export const blindAudioUrl = (id: string) => `${API_BASE_URL}${root}/reviewer-assignments/${encodeURIComponent(id)}/audio`;
