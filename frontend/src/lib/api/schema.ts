import { z } from "zod";
import { writingTaskTypeSchema } from "@/features/writing/task-types";

export const versionSchema = z.object({
  id: z.string().uuid(),
  version_number: z.number().int().positive(),
  status: z.enum(["DRAFT", "PUBLISHED", "ARCHIVED"]),
  created_at: z.string(),
  published_at: z.string().nullable(),
});

export const testSchema = z.object({
  published_detail: z.lazy(() => versionDetailSchema).nullish(),
  id: z.string().uuid(),
  title: z.string(),
  origin: z.enum(["ADMIN", "TEACHER"]).optional(),
  owner_user_id: z.string().uuid().nullable().optional(),
  owner_display_name: z.string().nullable().optional(),
  description: z.string().nullable(),
  source_label: z.string().nullable(),
  test_number: z.number().int().nullable(),
  archived_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  versions: z.array(versionSchema),
});

export const moduleSchema = z.object({
  id: z.string().uuid(),
  module_type: z.enum(["READING", "LISTENING", "WRITING", "SPEAKING"]),
  title: z.string().nullable(),
  recommended_duration_seconds: z.number().int().nullable(),
  passage_count: z.number().int(),
  listening_part_count: z.number().int(),
  writing_task_count: z.number().int(),
  question_count: z.number().int(),
  has_audio: z.boolean().optional(),
  reading_passages: z.array(z.object({
    id: z.string().uuid(),
    title: z.string(), order_index: z.number().int(),
    question_groups: z.array(z.object({ question_type: z.string(), start_number: z.number().int(), end_number: z.number().int(), question_count: z.number().int().nonnegative() })),
  })).optional(),
  listening_sections: z.array(z.object({
    id: z.string().uuid(),
    title: z.string().nullable(), order_index: z.number().int(),
    audio_start_seconds: z.number().int().nullable().optional(),
    audio_end_seconds: z.number().int().nullable().optional(),
    question_groups: z.array(z.object({ question_type: z.string(), start_number: z.number().int(), end_number: z.number().int(), question_count: z.number().int().nonnegative() })),
  })).optional(),
  writing_tasks: z.array(z.object({
    id: z.string().uuid(),
    task_number: z.number().int(), task_type: writingTaskTypeSchema.nullable(), prompt_excerpt: z.string().nullable(),
    minimum_recommended_words: z.number().int().nullable(),
    recommended_duration_seconds: z.number().int().nullable(),
  })).optional(),
  speaking_parts: z.array(z.object({
    id: z.string().uuid(),
    part_number: z.union([z.literal(1), z.literal(2), z.literal(3)]),
    order_index: z.number().int().nonnegative(),
    title: z.string().nullable(),
    prompts: z.array(z.object({
      id: z.string().uuid(),
      order_index: z.number().int().nonnegative(),
      prompt_type: z.enum(["SHORT_ANSWER", "LONG_TURN", "FOLLOW_UP"]),
      prompt_text: z.string(),
      cue_points: z.array(z.string()),
    })),
  })).optional(),
});

export const versionDetailSchema = versionSchema.extend({
  test_id: z.string().uuid(),
  test_title: z.string(),
  modules: z.array(moduleSchema),
});

export type TestSummary = z.infer<typeof testSchema>;
export type VersionDetail = z.infer<typeof versionDetailSchema>;
