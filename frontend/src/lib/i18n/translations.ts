import { en } from "./en";
import { vi } from "./vi";
import type { Locale, TranslationKey, TranslationParams } from "./types";

export function translate(locale: Locale, key: TranslationKey, params?: TranslationParams): string {
  const message = (locale === "vi" ? vi[key] : en[key]) ?? en[key];
  return message.replace(/\{([a-zA-Z][a-zA-Z0-9_]*)\}/g, (token, name: string) =>
    params && Object.hasOwn(params, name) ? String(params[name]) : token,
  );
}

export const moduleTranslationKeys: Record<"READING" | "LISTENING" | "WRITING", TranslationKey> = {
  READING: "common.reading", LISTENING: "common.listening", WRITING: "common.writing",
};

export const statusTranslationKeys: Readonly<Record<string, TranslationKey>> = {
  DRAFT: "common.draft", PUBLISHED: "common.published", ARCHIVED: "common.archived",
  IN_PROGRESS: "common.inProgress", PAUSED: "common.paused", SUBMITTED: "common.submitted",
  AUTO_SUBMITTED: "common.autoSubmitted", INTERRUPTED: "common.interrupted", ABANDONED: "common.abandoned",
};

export const questionTypeTranslationKeys: Readonly<Record<string, TranslationKey>> = {
  multiple_choice: "common.questionType.multiple_choice",
  multiple_choice_multiple: "common.questionType.multiple_choice_multiple",
  true_false_not_given: "common.questionType.true_false_not_given",
  yes_no_not_given: "common.questionType.yes_no_not_given",
  text_completion: "common.questionType.text_completion",
  matching_headings: "common.questionType.matching_headings",
  matching: "common.questionType.matching",
  matching_information: "common.questionType.matching_information",
  matching_features: "common.questionType.matching_features",
  matching_sentence_endings: "common.questionType.matching_sentence_endings",
  summary_completion_word_list: "common.questionType.summary_completion_word_list",
  plan_labelling: "common.questionType.plan_labelling",
  map_labelling: "common.questionType.map_labelling",
  diagram_labelling: "common.questionType.diagram_labelling",
  form_completion: "common.questionType.form_completion",
  note_completion: "common.questionType.note_completion",
  table_completion: "common.questionType.table_completion",
  flow_chart_completion: "common.questionType.flow_chart_completion",
  summary_completion: "common.questionType.summary_completion",
  sentence_completion: "common.questionType.sentence_completion",
  short_answer: "common.questionType.short_answer",
};

export const writingTaskTranslationKeys: Record<import("@/features/writing/task-types").WritingTaskType, TranslationKey> = {
  LINE_GRAPH: "common.writingType.LINE_GRAPH",
  BAR_CHART: "common.writingType.BAR_CHART",
  PIE_CHART: "common.writingType.PIE_CHART",
  TABLE: "common.writingType.TABLE",
  MIXED_CHARTS: "common.writingType.MIXED_CHARTS",
  PROCESS: "common.writingType.PROCESS",
  MAP_PLAN: "common.writingType.MAP_PLAN",
  OBJECT_SYSTEM_DIAGRAM: "common.writingType.OBJECT_SYSTEM_DIAGRAM",
  OTHER_VISUAL: "common.writingType.OTHER_VISUAL",
  OPINION: "common.writingType.OPINION",
  DISCUSS_BOTH_VIEWS: "common.writingType.DISCUSS_BOTH_VIEWS",
  DISCUSS_BOTH_VIEWS_AND_OPINION: "common.writingType.DISCUSS_BOTH_VIEWS_AND_OPINION",
  ADVANTAGES_DISADVANTAGES: "common.writingType.ADVANTAGES_DISADVANTAGES",
  ADVANTAGES_OUTWEIGH_DISADVANTAGES: "common.writingType.ADVANTAGES_OUTWEIGH_DISADVANTAGES",
  PROBLEM_SOLUTION: "common.writingType.PROBLEM_SOLUTION",
  CAUSE_SOLUTION: "common.writingType.CAUSE_SOLUTION",
  TWO_PART_QUESTION: "common.writingType.TWO_PART_QUESTION",
  OTHER_ESSAY: "common.writingType.OTHER_ESSAY",
};
