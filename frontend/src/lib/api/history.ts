import { z } from "zod";
import { apiRequest } from "./client";

const historyItemSchema = z.object({
  attempt_id: z.string().uuid(),
  test_title: z.string(),
  version_number: z.number().int(),
  module: z.enum(["READING", "LISTENING", "WRITING"]),
  status: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  elapsed_seconds: z.number().int().nullable(),
  raw_score: z.number().int().nullable(),
  max_score: z.number().int().nullable(),
});

const historySchema = z.object({ items: z.array(historyItemSchema), total: z.number().int() });
export type HistoryItem = z.infer<typeof historyItemSchema>;

export async function getHistory() {
  return historySchema.parse(await apiRequest<unknown>("/history"));
}
