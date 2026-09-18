import { z } from "zod";

export const versionSchema = z.object({
  id: z.string().uuid(),
  version_number: z.number().int().positive(),
  status: z.enum(["DRAFT", "PUBLISHED", "ARCHIVED"]),
  created_at: z.string(),
  published_at: z.string().nullable(),
});

export const testSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  description: z.string().nullable(),
  source_label: z.string().nullable(),
  test_number: z.number().int().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  versions: z.array(versionSchema),
});

export const moduleSchema = z.object({
  id: z.string().uuid(),
  module_type: z.enum(["READING", "LISTENING", "WRITING"]),
  title: z.string().nullable(),
  recommended_duration_seconds: z.number().int().nullable(),
  passage_count: z.number().int(),
  listening_part_count: z.number().int(),
  writing_task_count: z.number().int(),
  question_count: z.number().int(),
});

export const versionDetailSchema = versionSchema.extend({
  test_id: z.string().uuid(),
  test_title: z.string(),
  modules: z.array(moduleSchema),
});

export type TestSummary = z.infer<typeof testSchema>;
export type VersionDetail = z.infer<typeof versionDetailSchema>;
