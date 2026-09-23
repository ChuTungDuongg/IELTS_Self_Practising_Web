import { z } from "zod";
import { apiRequest, type ApiRequester } from "./client";

const historyItemSchema = z.object({
  attempt_id: z.string().uuid(),
  test_id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  test_session_id: z.string().uuid().nullable().optional(),
  test_title: z.string(),
  version_number: z.number().int(),
  module: z.enum(["READING", "LISTENING", "WRITING"]),
  status: z.enum(["IN_PROGRESS", "PAUSED", "SUBMITTED", "AUTO_SUBMITTED", "INTERRUPTED", "ABANDONED"]),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  elapsed_seconds: z.number().int().nullable(),
  timer_mode: z.enum(["COUNTDOWN", "COUNT_UP"]),
  timer_limit_seconds: z.number().int().nullable(),
  remaining_seconds: z.number().int().nullable(),
  raw_score: z.number().int().nullable(),
  max_score: z.number().int().nullable(),
  band_score: z.number().nullable(),
  review_available: z.boolean().optional(),
});

const historyGroupSchema = z.object({
  test_id: z.string().uuid(),
  test_version_id: z.string().uuid(),
  test_title: z.string(),
  version_number: z.number().int(),
  reading: historyItemSchema.nullable(),
  listening: historyItemSchema.nullable(),
  writing: historyItemSchema.nullable(),
  overall_band_score: z.number().nullable(),
});

const historySchema = z.object({
  items: z.array(historyItemSchema),
  groups: z.array(historyGroupSchema),
  sessions: z.array(z.object({ session_id: z.string().uuid(), test_version_id: z.string().uuid(), test_title: z.string(), version_number: z.number().int(), status: z.enum(["IN_PROGRESS", "COMPLETED", "ABANDONED"]), started_at: z.string(), finished_at: z.string().nullable(), reading: historyItemSchema.nullable(), listening: historyItemSchema.nullable(), writing: historyItemSchema.nullable(), overall_band_score: z.number().nullable() })).optional(),
  total: z.number().int(),
});
export type HistoryItem = z.infer<typeof historyItemSchema>;
export type HistoryGroup = z.infer<typeof historyGroupSchema>;
export type HistoryResponse = z.infer<typeof historySchema>;
export type MockHistoryGroup = NonNullable<HistoryResponse["sessions"]>[number];

export async function getHistory(request: ApiRequester = apiRequest): Promise<HistoryResponse> {
  return historySchema.parse(await request<unknown>("/history"));
}
