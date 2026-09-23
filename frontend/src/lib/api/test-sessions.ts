import { z } from "zod";
import { attemptResponseSchema } from "./attempts";
import { apiRequest, type ApiRequester } from "./client";

const moduleSchema = z.enum(["LISTENING", "READING", "WRITING"]);
const sessionAttemptSchema = z.object({
  attempt_id: z.string().uuid(), module: moduleSchema, status: z.string(),
  band_score: z.number().nullable(), raw_score: z.number().int().nullable(),
  max_score: z.number().int().nullable(), elapsed_seconds: z.number().int().nullable(),
});
export const testSessionSchema = z.object({
  session_id: z.string().uuid(), test_version_id: z.string().uuid(), test_title: z.string(),
  version_number: z.number().int(), status: z.enum(["IN_PROGRESS", "COMPLETED", "ABANDONED"]),
  started_at: z.string(), finished_at: z.string().nullable(), current_module: moduleSchema.nullable(),
  next_module: moduleSchema.nullable(), current_attempt: attemptResponseSchema.nullable(),
  attempts: z.array(sessionAttemptSchema), warnings: z.array(z.string()), overall_band_score: z.number().nullable(),
});
export type TestSession = z.infer<typeof testSessionSchema>;

export async function startTestSession(testVersionId: string) {
  const result = await apiRequest<unknown>("/test-sessions", { method: "POST", body: JSON.stringify({ test_version_id: testVersionId }) });
  return z.object({ session: testSessionSchema, current_attempt: attemptResponseSchema }).parse(result);
}
export async function getTestSession(sessionId: string, request: ApiRequester = apiRequest): Promise<TestSession> {
  return testSessionSchema.parse(await request<unknown>(`/test-sessions/${sessionId}`));
}
export async function advanceTestSession(sessionId: string): Promise<TestSession> {
  return testSessionSchema.parse(await apiRequest<unknown>(`/test-sessions/${sessionId}/advance`, { method: "POST" }));
}
