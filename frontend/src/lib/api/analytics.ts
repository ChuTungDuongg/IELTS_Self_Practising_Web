import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";

const skillSchema = z.enum(["READING", "LISTENING", "WRITING"]);
const accuracySchema = z.object({ question_type: z.string(), attempted: z.number().int(), correct: z.number().int(), incorrect: z.number().int(), accuracy: z.number().nullable() });
const bandSummarySchema = z.object({ latest: z.number().nullable(), best: z.number().nullable(), average: z.number().nullable() });
export const analyticsSchema = z.object({
  total_finalized_attempts: z.number().int(), total_active_seconds: z.number().int(), average_attempt_seconds: z.number().nullable(),
  bands: z.record(z.string(), bandSummarySchema), completed_full_mocks: z.number().int(), latest_project_overall: z.number().nullable(),
  latest_full_mock: z.object({ session_id: z.string().uuid(), test_title: z.string(), finished_at: z.string(), reading_band: z.number().nullable(), listening_band: z.number().nullable(), writing_band: z.number().nullable(), overall_band: z.number().nullable() }).nullable(),
  trends: z.array(z.object({ attempt_id: z.string().uuid(), skill: skillSchema, band_score: z.number(), attempted_at: z.string(), test_title: z.string(), version_number: z.number().int() })),
  question_types: z.array(accuracySchema), weak_areas: z.array(accuracySchema),
  attempts: z.array(z.object({ attempt_id: z.string().uuid(), skill: skillSchema, label: z.string(), band_score: z.number().nullable(), finished_at: z.string() })),
  content_timing: z.array(z.object({ attempt_id: z.string().uuid(), kind: z.string(), target_id: z.string().uuid(), active_seconds: z.number().int() })),
});
const sideSchema = z.object({ attempt_id: z.string().uuid(), skill: skillSchema, test_title: z.string(), version_number: z.number().int(), band_score: z.number().nullable(), raw_score: z.number().int().nullable(), max_score: z.number().int().nullable(), elapsed_seconds: z.number().int().nullable(), accuracy: z.number().nullable(), question_types: z.array(accuracySchema), writing: z.object({ task1_overall: z.number().nullable(), task2_overall: z.number().nullable(), ta: z.number().nullable(), cc: z.number().nullable(), lr: z.number().nullable(), gra: z.number().nullable() }).nullable() });
const comparisonSchema = z.object({ same_skill: z.boolean(), same_test_version: z.boolean(), left: sideSchema, right: sideSchema });
export type AnalyticsDashboard = z.infer<typeof analyticsSchema>;
export type AttemptComparison = z.infer<typeof comparisonSchema>;

export async function getAnalytics(skill?: "READING" | "LISTENING" | "WRITING", request: ApiRequester = apiRequest): Promise<AnalyticsDashboard> {
  return analyticsSchema.parse(await request<unknown>(`/analytics${skill ? `?skill=${skill}` : ""}`));
}
export async function compareAttempts(left: string, right: string): Promise<AttemptComparison> {
  return comparisonSchema.parse(await apiRequest<unknown>(`/analytics/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`));
}
