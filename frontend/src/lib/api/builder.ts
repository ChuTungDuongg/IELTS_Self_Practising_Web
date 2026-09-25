import { z } from "zod";
import type { QuestionGroupModel } from "@/features/questions/types";
import { apiRequest, type ApiRequester } from "./client";
import { writingTaskTypeSchema, type WritingTaskType } from "@/features/writing/task-types";

const blockSchema = z.object({
  id: z.string().uuid(),
  type: z.enum(["paragraph", "heading"]),
  label: z.string().nullable().optional(),
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
  revision: z.number().int().positive(),
  question_type: z.enum(["multiple_choice", "multiple_choice_multiple", "true_false_not_given", "yes_no_not_given", "text_completion", "matching_headings", "matching", "matching_information", "matching_features", "matching_sentence_endings", "summary_completion_word_list", "plan_labelling", "map_labelling", "diagram_labelling", "form_completion", "note_completion", "table_completion", "flow_chart_completion", "summary_completion", "sentence_completion", "short_answer"]),
  instruction: z.string(),
  config: z.record(z.string(), z.unknown()),
  order_index: z.number().int(),
  questions: z.array(questionSchema),
  image_asset_id: z.string().uuid().nullable().optional(),
  image_asset: z.object({ id: z.string().uuid(), original_name: z.string(), mime_type: z.string(), file_size: z.number(), content_url: z.string() }).nullable().optional(),
});

const passageSchema = z.object({
  id: z.string().uuid(),
  revision: z.number().int().positive(),
  title: z.string(),
  order_index: z.number().int(),
  blocks: z.array(blockSchema),
  question_groups: z.array(groupSchema),
});

const assetSchema = z.object({ id: z.string().uuid(), original_name: z.string(), mime_type: z.string(), file_size: z.number(), content_url: z.string() });
const listeningPartSchema = z.object({
  id: z.string().uuid(), revision: z.number().int().positive(), title: z.string().nullable(), order_index: z.number().int(),
  question_groups: z.array(groupSchema),
});
const builderWritingTaskSchema = z.object({
  id: z.string().uuid(),
  revision: z.number().int().positive(),
  task_number: z.number().int(),
  task_type: writingTaskTypeSchema.nullable().optional(),
  prompt: z.string(),
  image_asset_id: z.string().uuid().nullable().default(null),
  image_asset: assetSchema.nullable().default(null),
  minimum_recommended_words: z.number().int().nullable(),
  recommended_duration_seconds: z.number().int().nullable(),
  order_index: z.number().int(),
});

const builderVersionSchema = z.object({
  id: z.string().uuid(),
  test_id: z.string().uuid(),
  test_title: z.string(),
  test_description: z.string().nullable().optional(),
  version_number: z.number().int(),
  status: z.enum(["DRAFT", "PUBLISHED", "ARCHIVED"]),
  modules: z.array(
    z.object({
      id: z.string().uuid(),
      revision: z.number().int().positive(),
      module_type: z.enum(["READING", "LISTENING", "WRITING"]),
      title: z.string().nullable(),
      recommended_duration_seconds: z.number().int().nullable(),
      audio_asset: assetSchema.nullable().default(null),
      passages: z.array(passageSchema).default([]),
      listening_parts: z.array(listeningPartSchema).default([]),
      writing_tasks: z.array(builderWritingTaskSchema).default([]),
    }),
  ),
});

export type BuilderVersion = z.infer<typeof builderVersionSchema>;
export type BuilderModule = BuilderVersion["modules"][number];
export type BuilderPassage = z.infer<typeof passageSchema>;
export type BuilderQuestionGroup = z.infer<typeof groupSchema>;
export type BuilderListeningPart = z.infer<typeof listeningPartSchema>;
export type BuilderWritingTask = z.infer<typeof builderWritingTaskSchema>;
export type TextBlock = z.infer<typeof blockSchema>;

export function parseBuilderVersion(value: unknown): BuilderVersion {
  return builderVersionSchema.parse(value);
}

export async function getBuilderVersion(versionId: string, request: ApiRequester = apiRequest): Promise<BuilderVersion> {
  return parseBuilderVersion(
    await request<unknown>(`/test-versions/${versionId}/builder`),
  );
}

export function createReadingModule(versionId: string) {
  return apiRequest(`/test-versions/${versionId}/modules`, {
    method: "POST",
    body: JSON.stringify({
      module_type: "READING",
      title: "Reading",
    }),
  });
}

export function createListeningModule(versionId: string) {
  return apiRequest(`/test-versions/${versionId}/modules`, { method: "POST", body: JSON.stringify({ module_type: "LISTENING", title: "Listening" }) });
}

export function createWritingModule(versionId: string) {
  return apiRequest(`/test-versions/${versionId}/modules`, {
    method: "POST",
    body: JSON.stringify({
      module_type: "WRITING",
      title: "Writing",
    }),
  });
}

export async function updateModuleDuration(moduleId: string, expectedRevision: number, seconds: number | null): Promise<BuilderModule> {
  return builderVersionSchema.shape.modules.element.parse(await apiRequest<unknown>(`/test-modules/${moduleId}`, {
    method: "PATCH",
    body: JSON.stringify({ expected_revision: expectedRevision, recommended_duration_seconds: seconds }),
  }));
}

export type WritingTaskUpdate = {
  expected_revision: number;
  prompt: string;
  task_type: WritingTaskType | null;
  image_asset_id: string | null;
  minimum_recommended_words: number | null;
  recommended_duration_seconds: number | null;
};

export async function updateWritingTask(taskId: string, body: WritingTaskUpdate) {
  return builderWritingTaskSchema.parse(await apiRequest<unknown>(`/writing/tasks/${taskId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  }));
}

export function deleteModule(moduleId: string) {
  return apiRequest(`/test-modules/${moduleId}`, { method: "DELETE" });
}

export function createListeningPart(versionId: string, body: { title: string; order_index: number }) {
  return apiRequest<BuilderListeningPart>(`/test-versions/${versionId}/listening/parts`, { method: "POST", body: JSON.stringify(body) });
}

export function updateListeningPart(partId: string, body: { expected_revision: number; title: string | null; order_index: number }) {
  return apiRequest<BuilderListeningPart>(`/listening/parts/${partId}`, { method: "PUT", body: JSON.stringify(body) });
}

export function deleteListeningPart(partId: string) { return apiRequest(`/listening/parts/${partId}`, { method: "DELETE" }); }

export function attachListeningAudio(moduleId: string, assetId: string | null, expectedRevision: number) {
  return apiRequest<BuilderVersion["modules"][number]>(`/listening/modules/${moduleId}/audio`, { method: "PUT", body: JSON.stringify({ asset_id: assetId, expected_revision: expectedRevision }) });
}

export function createListeningQuestionGroup(partId: string, body: QuestionGroupModel) {
  return apiRequest<BuilderQuestionGroup>(`/listening/parts/${partId}/question-groups`, { method: "POST", body: JSON.stringify(body) });
}

export function updateListeningQuestionGroup(groupId: string, body: QuestionGroupModel, expectedRevision: number) {
  return apiRequest<BuilderQuestionGroup>(`/listening/question-groups/${groupId}`, { method: "PUT", body: JSON.stringify({ ...body, expected_revision: expectedRevision }) });
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
  body: { expected_revision: number; title: string; order_index: number; blocks: TextBlock[] },
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
  expectedRevision: number,
) {
  return groupSchema.parse(
    await apiRequest<unknown>(`/question-groups/${groupId}`, {
      method: "PUT",
      body: JSON.stringify({ ...body, expected_revision: expectedRevision }),
    }),
  );
}

export function deleteQuestionGroup(groupId: string) {
  return apiRequest(`/question-groups/${groupId}`, { method: "DELETE" });
}

export function deletePassage(passageId: string) {
  return apiRequest(`/reading/passages/${passageId}`, { method: "DELETE" });
}

export function reorderQuestionGroups(moduleId: string, groupIds: string[], expectedRevision: number) {
  return apiRequest<BuilderVersion["modules"][number]>(`/test-modules/${moduleId}/question-groups/order`, {
    method: "PUT",
    body: JSON.stringify({ group_ids: groupIds, expected_revision: expectedRevision }),
  });
}
