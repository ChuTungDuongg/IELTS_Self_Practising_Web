import type { BuilderVersion } from "@/lib/api/builder";
import type { VersionDetail } from "@/lib/api/schema";
import type { WritingTaskType } from "@/features/writing/task-types";

export type SummaryUnit = {
  heading: { message: "common.passageNumber" | "common.sectionNumber" | "common.taskNumber" | "speaking.part"; params: { number: number } };
  title: string | null;
  questionTypes?: string[];
  taskType?: WritingTaskType | null;
  excerpt?: string | null;
  prompts?: Array<{
    ordinal: number;
    text: string;
    type: "SHORT_ANSWER" | "LONG_TURN" | "FOLLOW_UP";
    cuePoints: string[];
  }>;
};

function uniqueTypes(groups: Array<{ question_type: string }>): string[] {
  return [...new Set(groups.map((group) => group.question_type))];
}

function excerpt(prompt: string): string | null {
  const text = prompt.replace(/\s+/g, " ").trim();
  return text ? `${text.slice(0, 140)}${text.length > 140 ? "…" : ""}` : null;
}

export function builderContentSummary(module: BuilderVersion["modules"][number] | undefined): SummaryUnit[] {
  if (!module) return [];
  if (module.module_type === "SPEAKING") return [...(module.speaking_parts ?? [])].sort((a, b) => a.order_index - b.order_index).map((part) => ({
    heading: { message: "speaking.part", params: { number: part.part_number } }, title: part.title,
    excerpt: excerpt(part.prompts.map(prompt => prompt.prompt_text).join(" ")),
  }));
  if (module.module_type === "READING") return [...module.passages].sort((a, b) => a.order_index - b.order_index).map((passage) => ({
    heading: { message: "common.passageNumber", params: { number: passage.order_index + 1 } }, title: passage.title,
    questionTypes: uniqueTypes([...passage.question_groups].sort((a, b) => a.order_index - b.order_index)),
  }));
  if (module.module_type === "LISTENING") return [...module.listening_parts].sort((a, b) => a.order_index - b.order_index).map((part) => ({
    heading: { message: "common.sectionNumber", params: { number: part.order_index + 1 } }, title: part.title,
    questionTypes: uniqueTypes([...part.question_groups].sort((a, b) => a.order_index - b.order_index)),
  }));
  return [...module.writing_tasks].sort((a, b) => a.order_index - b.order_index).map((task) => ({
    heading: { message: "common.taskNumber", params: { number: task.task_number } }, title: null, taskType: task.task_type ?? null, excerpt: excerpt(task.prompt),
  }));
}

export function publishedContentSummary(module: VersionDetail["modules"][number]): SummaryUnit[] {
  if (module.module_type === "SPEAKING") return [...(module.speaking_parts ?? [])].sort((a, b) => a.order_index - b.order_index).map((part) => ({
    heading: { message: "speaking.part", params: { number: part.part_number } }, title: part.title,
    prompts: [...part.prompts].sort((a, b) => a.order_index - b.order_index).map((prompt, index) => ({
      ordinal: index + 1, text: prompt.prompt_text, type: prompt.prompt_type, cuePoints: prompt.cue_points,
    })),
  }));
  if (module.module_type === "READING") return [...(module.reading_passages ?? [])].sort((a, b) => a.order_index - b.order_index).map((passage) => ({
    heading: { message: "common.passageNumber", params: { number: passage.order_index + 1 } }, title: passage.title, questionTypes: uniqueTypes(passage.question_groups),
  }));
  if (module.module_type === "LISTENING") return [...(module.listening_sections ?? [])].sort((a, b) => a.order_index - b.order_index).map((part) => ({
    heading: { message: "common.sectionNumber", params: { number: part.order_index + 1 } }, title: part.title, questionTypes: uniqueTypes(part.question_groups),
  }));
  return [...(module.writing_tasks ?? [])].sort((a, b) => a.task_number - b.task_number).map((task) => ({
    heading: { message: "common.taskNumber", params: { number: task.task_number } }, title: null, taskType: task.task_type, excerpt: task.prompt_excerpt,
  }));
}

export { ContentSummary } from "./content-summary-view";
