import { z } from "zod";
import type { QuestionGroupModel } from "@/features/questions/types";
import { apiRequest } from "./client";

const blockSchema = z.object({
  id: z.string().uuid(),
  type: z.enum(["paragraph", "heading"]),
  text: z.string(),
});

const questionSchema = z.object({
  id: z.string().uuid(),
  number: z.number().int(),
  prompt: z.string(),
  config: z.record(z.string(), z.unknown()),
  answer_key: z.record(z.string(), z.unknown()),
  explanation: z.string().nullable(),
  order_index: z.number().int(),
});

const groupSchema = z.object({
  id: z.string().uuid(),
  question_type: z.enum([
    "multiple_choice",
    "true_false_not_given",
    "text_completion",
    "matching_headings",
  ]),
  instruction: z.string(),
  config: z.record(z.string(), z.unknown()),
  order_index: z.number().int(),
  questions: z.array(questionSchema),
});

const passageSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  order_index: z.number().int(),
  blocks: z.array(blockSchema),
  question_groups: z.array(groupSchema),
});

const builderVersionSchema = z.object({
  id: z.string().uuid(),
  test_id: z.string().uuid(),
  test_title: z.string(),
  version_number: z.number().int(),
  status: z.enum(["DRAFT", "PUBLISHED", "ARCHIVED"]),
  modules: z.array(
    z.object({
      id: z.string().uuid(),
      module_type: z.enum(["READING", "LISTENING", "WRITING"]),
      title: z.string().nullable(),
      recommended_duration_seconds: z.number().int().nullable(),
      passages: z.array(passageSchema),
    }),
  ),
});

export type BuilderVersion = z.infer<typeof builderVersionSchema>;
export type BuilderPassage = z.infer<typeof passageSchema>;
export type BuilderQuestionGroup = z.infer<typeof groupSchema>;
export type TextBlock = z.infer<typeof blockSchema>;

export async function getBuilderVersion(versionId: string): Promise<BuilderVersion> {
  return builderVersionSchema.parse(
    await apiRequest<unknown>(`/test-versions/${versionId}/builder`),
  );
}

export function createReadingModule(versionId: string) {
  return apiRequest(`/test-versions/${versionId}/modules`, {
    method: "POST",
    body: JSON.stringify({
      module_type: "READING",
      title: "Reading",
      recommended_duration_seconds: 3600,
    }),
  });
}

export async function createPassage(
  versionId: string,
  body: { title: string; order_index: number; blocks: TextBlock[] },
) {
  return passageSchema.parse(
    await apiRequest<unknown>(`/test-versions/${versionId}/reading/passages`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function updatePassage(
  passageId: string,
  body: { title: string; order_index: number; blocks: TextBlock[] },
) {
  return passageSchema.parse(
    await apiRequest<unknown>(`/reading/passages/${passageId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export async function createQuestionGroup(
  passageId: string,
  body: QuestionGroupModel,
) {
  return groupSchema.parse(
    await apiRequest<unknown>(`/reading/passages/${passageId}/question-groups`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function updateQuestionGroup(
  groupId: string,
  body: QuestionGroupModel,
) {
  return groupSchema.parse(
    await apiRequest<unknown>(`/question-groups/${groupId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  );
}

export function deleteQuestionGroup(groupId: string) {
  return apiRequest(`/question-groups/${groupId}`, { method: "DELETE" });
}

export function deletePassage(passageId: string) {
  return apiRequest(`/reading/passages/${passageId}`, { method: "DELETE" });
}
