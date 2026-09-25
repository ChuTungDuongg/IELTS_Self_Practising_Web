import type { BuilderVersion } from "@/lib/api/builder";
import type { VersionDetail } from "@/lib/api/schema";
import { questionTypeLabel } from "@/features/questions/question-type-meta";
import { writingTaskTypeLabel, type WritingTaskType } from "@/features/writing/task-types";

type SummaryUnit = {
  heading: string;
  title: string | null;
  questionTypes?: string[];
  taskType?: WritingTaskType | null;
  excerpt?: string | null;
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
  if (module.module_type === "READING") return [...module.passages].sort((a, b) => a.order_index - b.order_index).map((passage, index) => ({
    heading: `Passage ${index + 1}`, title: passage.title,
    questionTypes: uniqueTypes([...passage.question_groups].sort((a, b) => a.order_index - b.order_index)),
  }));
  if (module.module_type === "LISTENING") return [...module.listening_parts].sort((a, b) => a.order_index - b.order_index).map((part, index) => ({
    heading: `Section ${index + 1}`, title: part.title,
    questionTypes: uniqueTypes([...part.question_groups].sort((a, b) => a.order_index - b.order_index)),
  }));
  return [...module.writing_tasks].sort((a, b) => a.order_index - b.order_index).map((task) => ({
    heading: `Task ${task.task_number}`, title: null, taskType: task.task_type ?? null, excerpt: excerpt(task.prompt),
  }));
}

export function publishedContentSummary(module: VersionDetail["modules"][number]): SummaryUnit[] {
  if (module.module_type === "READING") return [...(module.reading_passages ?? [])].sort((a, b) => a.order_index - b.order_index).map((passage, index) => ({
    heading: `Passage ${index + 1}`, title: passage.title, questionTypes: uniqueTypes(passage.question_groups),
  }));
  if (module.module_type === "LISTENING") return [...(module.listening_sections ?? [])].sort((a, b) => a.order_index - b.order_index).map((part, index) => ({
    heading: `Section ${index + 1}`, title: part.title, questionTypes: uniqueTypes(part.question_groups),
  }));
  return [...(module.writing_tasks ?? [])].sort((a, b) => a.task_number - b.task_number).map((task) => ({
    heading: `Task ${task.task_number}`, title: null, taskType: task.task_type, excerpt: task.prompt_excerpt,
  }));
}

export function ContentSummary({ units }: { units: SummaryUnit[] }) {
  if (!units.length) return <p className="mt-4 text-sm text-[var(--muted)]">No content added yet.</p>;
  return <div className="mt-4 space-y-3">
    {units.map((unit) => <div key={unit.heading} className="border-t border-[var(--border)] pt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{unit.heading}</p>
      {unit.title ? <p className="mt-1 text-sm font-semibold">{unit.title}</p> : null}
      {unit.questionTypes ? <div className="mt-2 flex flex-wrap gap-1.5">{unit.questionTypes.map((type) => <span key={type} className="rounded-full border border-[var(--border)] px-2 py-0.5 text-xs">{questionTypeLabel(type)}</span>)}</div> : null}
      {unit.taskType !== undefined ? <span className="mt-2 inline-block rounded-full border border-[var(--border)] px-2 py-0.5 text-xs">{writingTaskTypeLabel(unit.taskType)}</span> : null}
      {unit.excerpt ? <p className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">{unit.excerpt}</p> : null}
    </div>)}
  </div>;
}
