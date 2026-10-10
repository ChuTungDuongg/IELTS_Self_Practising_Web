"use client";

import { useState } from "react";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { writingTaskTypeLabel } from "@/features/writing/task-types";
import type { VersionDetail } from "@/lib/api/schema";
import { StartFocusedPractice } from "./start-focused-practice";

type GroupSummary = { start_number: number; end_number: number; question_count: number };

function questionSummary(groups: GroupSummary[]): string {
  const count = groups.reduce((sum, group) => sum + group.question_count, 0);
  const sorted = [...groups].sort((left, right) => left.start_number - right.start_number);
  const contiguous = sorted.length > 0 && sorted.every((group, index) =>
    group.question_count === group.end_number - group.start_number + 1
    && (index === 0 || group.start_number === sorted[index - 1].end_number + 1));
  const total = `${count} ${count === 1 ? "question" : "questions"}`;
  if (!contiguous) return total;
  const start = sorted[0].start_number;
  const end = sorted[sorted.length - 1].end_number;
  return `${start === end ? `Question ${start}` : `Questions ${start}–${end}`} · ${total}`;
}

export function SkillPractice({ versions }: { versions: VersionDetail[] }) {
  const [skill, setSkill] = useState<"READING" | "WRITING">("READING");
  const available = versions.filter((version) => version.modules.some((module) =>
    module.module_type === skill && (skill === "READING" ? module.reading_passages?.length : module.writing_tasks?.length)));

  return <>
    <div className="history-tabs mb-6" role="tablist" aria-label="Practice skill">
      {(["READING", "WRITING"] as const).map((module) => <button type="button" key={module} id={`practice-tab-${module}`} role="tab" aria-selected={skill === module} aria-controls="practice-units" className={`btn ${skill === module ? "btn-primary" : "btn-secondary"}`} onClick={() => setSkill(module)}>{module === "READING" ? "Reading" : "Writing"}</button>)}
    </div>
    <div id="practice-units" role="tabpanel" aria-labelledby={`practice-tab-${skill}`}>
      {available.length ? available.map((version) => <section key={`${skill}-${version.id}`} className="mb-8" aria-labelledby={`practice-version-${version.id}`}>
        <div className="mb-4 border-b border-[var(--line)] pb-3">
          <h2 id={`practice-version-${version.id}`} className="text-xl font-semibold">{version.test_title}</h2>
          <p className="practice-version mt-1">Version {version.version_number}</p>
        </div>
        <div className="practice-grid">
          {version.modules.filter((module) => module.module_type === skill).flatMap((module) => skill === "READING"
            ? [...(module.reading_passages ?? [])].sort((a, b) => a.order_index - b.order_index).map((passage) => <article key={passage.id} className="practice-card">
              <div className="practice-card-accent" aria-hidden="true" />
              <div className="practice-card-content">
                <ModuleBadge module="READING" />
                <div className="practice-card-title"><p className="practice-module-kicker">Passage {passage.order_index + 1}</p><h3 className="mt-2 text-lg font-semibold">{passage.title}</h3><span>{questionSummary(passage.question_groups)}</span></div>
                <StartFocusedPractice versionId={version.id} target={{ module: "READING", unitId: passage.id }} />
              </div>
            </article>)
            : [...(module.writing_tasks ?? [])].sort((a, b) => a.task_number - b.task_number).map((task) => <article key={task.id} className="practice-card practice-card-writing">
              <div className="practice-card-accent" aria-hidden="true" />
              <div className="practice-card-content">
                <ModuleBadge module="WRITING" />
                <div className="practice-card-title"><p className="practice-module-kicker">{writingTaskTypeLabel(task.task_type)}</p><h3 className="mt-2 text-lg font-semibold">Task {task.task_number}</h3><span>{task.prompt_excerpt ?? "Open this task to read the prompt."}</span></div>
                {task.minimum_recommended_words !== null ? <p className="mt-3 text-sm text-[var(--muted)]">Recommended {task.minimum_recommended_words}+ words</p> : null}
                <StartFocusedPractice versionId={version.id} target={{ module: "WRITING", unitId: task.id, taskNumber: task.task_number }} />
              </div>
            </article>))}
        </div>
      </section>) : <EmptyState title={`No ${skill === "READING" ? "Reading passages" : "Writing tasks"} available`} description="Published tests with this skill will appear here when available." />}
    </div>
  </>;
}
