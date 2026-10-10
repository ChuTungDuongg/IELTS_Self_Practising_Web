"use client";

import { useMemo, useState, type ComponentProps } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { formatAudioTime, sectionAudioClip, validAudioClip } from "@/features/listening/audio-time";
import { moduleTranslationKeys, writingTaskTranslationKeys, translate } from "@/lib/i18n/translations";
import type { TranslationFunction } from "@/lib/i18n/types";
import { writingTaskTypeLabel } from "@/features/writing/task-types";
import type { VersionDetail } from "@/lib/api/schema";
import { StartFocusedPractice } from "./start-focused-practice";

type Skill = keyof typeof moduleTranslationKeys;
const skillOrder: Skill[] = ["READING", "LISTENING", "WRITING"];
type Selection = { skill: Skill; unitIndex: number | null };
type PracticeUnit = {
  versionId: string;
  testTitle: string;
  versionNumber: number;
  target: ComponentProps<typeof StartFocusedPractice>["target"];
  unitIndex: number;
  title: string;
  typeLabel?: string;
  description?: string;
  summary: string | null;
  audioStatus?: string;
  groups?: GroupSummary[];
  generatedTitle?: boolean;
  promptFallback?: boolean;
  taskType?: keyof typeof writingTaskTranslationKeys | null;
  words?: number | null;
  audio?: { kind: "none" | "full" | "clip"; start?: number; end?: number };
};
type GroupSummary = { start_number: number; end_number: number; question_count: number };

function questionSummary(groups: GroupSummary[], t: TranslationFunction = (key, params) => translate("en", key, params)): string {
  const count = groups.reduce((sum, group) => sum + group.question_count, 0);
  const sorted = [...groups].sort((left, right) => left.start_number - right.start_number);
  const contiguous = sorted.length > 0 && sorted.every((group, index) =>
    group.question_count === group.end_number - group.start_number + 1
    && (index === 0 || group.start_number === sorted[index - 1].end_number + 1));
  const total = t(count === 1 ? "common.questionCount" : "common.questionsCount", { count });
  if (!contiguous) return total;
  const start = sorted[0].start_number;
  const end = sorted[sorted.length - 1].end_number;
  return `${start === end ? t("runner.question", { number: start }) : t("common.questionsRange", { start, end })} · ${total}`;
}

function practiceUnits(versions: VersionDetail[]): PracticeUnit[] {
  return versions.flatMap((version) => version.modules.flatMap((module): PracticeUnit[] => {
    const provenance = { versionId: version.id, testTitle: version.test_title, versionNumber: version.version_number };
    if (module.module_type === "READING") {
      return [...(module.reading_passages ?? [])].sort((a, b) => a.order_index - b.order_index).map((passage) => ({
        ...provenance, target: { module: "READING", unitId: passage.id }, unitIndex: passage.order_index + 1,
        title: passage.title, summary: questionSummary(passage.question_groups), groups: passage.question_groups,
      }));
    }
    if (module.module_type === "LISTENING") {
      return [...(module.listening_sections ?? [])].sort((a, b) => a.order_index - b.order_index).map((section) => {
        const clip = sectionAudioClip(section);
        const audioStatus = !module.has_audio ? "No recording attached · external audio can be used"
          : clip && validAudioClip(clip) ? `Audio ${formatAudioTime(clip.startSeconds)}–${formatAudioTime(clip.endSeconds)} · ${formatAudioTime(clip.endSeconds - clip.startSeconds)}`
            : "Full recording available";
        return {
          ...provenance, target: { module: "LISTENING", unitId: section.id }, unitIndex: section.order_index + 1,
          title: section.title ?? `Section ${section.order_index + 1}`, summary: questionSummary(section.question_groups), groups: section.question_groups, generatedTitle: section.title === null, audioStatus,
          audio: { kind: !module.has_audio ? "none" : clip && validAudioClip(clip) ? "clip" : "full", start: clip?.startSeconds, end: clip?.endSeconds },
        };
      });
    }
    return [...(module.writing_tasks ?? [])].sort((a, b) => a.task_number - b.task_number).map((task) => ({
      ...provenance, target: { module: "WRITING", unitId: task.id, taskNumber: task.task_number }, unitIndex: task.task_number,
      title: `Task ${task.task_number}`, generatedTitle: true, typeLabel: writingTaskTypeLabel(task.task_type), taskType: task.task_type, promptFallback: task.prompt_excerpt === null, words: task.minimum_recommended_words,
      description: task.prompt_excerpt ?? "Open this task to read the prompt.",
      summary: task.minimum_recommended_words !== null ? `Recommended ${task.minimum_recommended_words}+ words` : null,
    }));
  }));
}

function PracticeFilterPanel({ units, selection, onSelect }: {
  units: PracticeUnit[];
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const { t } = useTranslation();
  return <nav className="practice-filter-panel" aria-label={t("practice.filters")}>
    <h2>{t("practice.filters")}</h2>
    {skillOrder.map((skill) => {
      const active = selection.skill === skill;
      const indexes = [...new Set(units.filter((unit) => unit.target.module === skill).map((unit) => unit.unitIndex))].sort((a, b) => a - b);
      return <div key={skill} data-skill={skill} className={`practice-filter-group${active ? " is-active" : ""}`} role="group" aria-label={t("practice.skillFilters", { skill: t(moduleTranslationKeys[skill]) })}>
        <button type="button" className="practice-filter-skill" aria-pressed={active} onClick={() => onSelect({ skill, unitIndex: null })}>{t(moduleTranslationKeys[skill])}</button>
        <div className="practice-unit-filters">
          <button type="button" className="practice-unit-filter" aria-current={active && selection.unitIndex === null ? "true" : undefined} onClick={() => onSelect({ skill, unitIndex: null })}>{t(skill === "READING" ? "practice.allPassages" : skill === "LISTENING" ? "practice.allSections" : "practice.allTasks")}</button>
          {indexes.map((unitIndex) => <button key={unitIndex} type="button" className="practice-unit-filter" aria-current={active && selection.unitIndex === unitIndex ? "true" : undefined} onClick={() => onSelect({ skill, unitIndex })}>{t(skill === "READING" ? "common.passageNumber" : skill === "LISTENING" ? "common.sectionNumber" : "common.taskNumber", { number: unitIndex })}</button>)}
        </div>
      </div>;
    })}
  </nav>;
}

function PracticeResultsHeader({ skill, search, onSearch }: { skill: Skill; search: string; onSearch: (value: string) => void }) {
  const { t } = useTranslation();
  return <header className="practice-results-header">
    <div><h2 id="practice-results-heading">{t(moduleTranslationKeys[skill])}</h2><p>{t(skill === "READING" ? "practice.readingSubtitle" : skill === "LISTENING" ? "practice.listeningSubtitle" : "practice.writingSubtitle")}</p></div>
    <input className="practice-search" type="search" aria-label={t("practice.search")} placeholder={t("practice.search")} value={search} onChange={(event) => onSearch(event.target.value)} />
  </header>;
}

function PracticeUnitCard({ unit, hidden }: { unit: PracticeUnit; hidden: boolean }) {
  const skill = unit.target.module;
  const { t } = useTranslation();
  const unitLabel = t(skill === "READING" ? "common.passageNumber" : skill === "LISTENING" ? "common.sectionNumber" : "common.taskNumber", { number: unit.unitIndex });
  return <article hidden={hidden} className={`practice-card practice-unit-card${skill === "LISTENING" ? " practice-card-listening" : skill === "WRITING" ? " practice-card-writing" : ""}`}>
    <div className="practice-card-content">
      <ModuleBadge module={skill} label={t(moduleTranslationKeys[skill])} />
      <div className="practice-card-title">
        {skill !== "WRITING" ? <p className="practice-module-kicker">{unitLabel}</p> : null}
        <h3>{unit.generatedTitle ? unitLabel : unit.title}</h3>
      </div>
      {unit.typeLabel ? <p className="practice-unit-type">{unit.taskType ? t(writingTaskTranslationKeys[unit.taskType]) : t("common.unclassified")}</p> : null}
      <p className="practice-unit-provenance">{unit.testTitle} · {t("common.versionNumber", { number: unit.versionNumber })}</p>
      {unit.description ? <p className="practice-unit-description">{unit.promptFallback ? t("practice.promptFallback") : unit.description}</p> : null}
      {unit.summary ? <p className="practice-unit-summary">{unit.groups ? questionSummary(unit.groups, t) : t("practice.recommendedWords", { count: unit.words ?? 0 })}</p> : null}
      {unit.audioStatus ? <p className="practice-unit-audio">{unit.audio?.kind === "none" ? t("practice.noRecording") : unit.audio?.kind === "full" ? t("practice.fullRecording") : t("practice.audioRange", { start: formatAudioTime(unit.audio?.start ?? 0), end: formatAudioTime(unit.audio?.end ?? 0), duration: formatAudioTime((unit.audio?.end ?? 0) - (unit.audio?.start ?? 0)) })}</p> : null}
      <StartFocusedPractice versionId={unit.versionId} target={unit.target} />
    </div>
  </article>;
}

export function SkillPractice({ versions }: { versions: VersionDetail[] }) {
  const { t } = useTranslation();
  const [selection, setSelection] = useState<Selection>({ skill: "READING", unitIndex: null });
  const [search, setSearch] = useState("");
  const units = useMemo(() => practiceUnits(versions), [versions]);
  const skillUnits = units.filter((unit) => unit.target.module === selection.skill);
  const query = search.trim().toLowerCase();
  const matches = skillUnits.filter((unit) => (selection.unitIndex === null || unit.unitIndex === selection.unitIndex)
    && [unit.testTitle, unit.title, unit.description, unit.typeLabel, `Version ${unit.versionNumber}`].some((value) => value?.toLowerCase().includes(query)));

  return <div className="practice-browser">
    <PracticeFilterPanel units={units} selection={selection} onSelect={setSelection} />
    <section className="practice-results" aria-labelledby="practice-results-heading">
      <PracticeResultsHeader skill={selection.skill} search={search} onSearch={setSearch} />
      {/* Keep controls mounted so filters preserve timers and pending-start guards. */}
      <div className="practice-grid" hidden={!matches.length}>
        {units.map((unit) => <PracticeUnitCard key={`${unit.versionId}-${unit.target.unitId}`} unit={unit} hidden={!matches.includes(unit)} />)}
      </div>
      {!matches.length ? <EmptyState title={skillUnits.length ? t("practice.noMatch") : t(selection.skill === "READING" ? "practice.noReading" : selection.skill === "LISTENING" ? "practice.noListening" : "practice.noWriting")} description={skillUnits.length ? t("practice.tryFilters") : t("practice.publishedContent", { skill: t(moduleTranslationKeys[selection.skill]) })} /> : null}
    </section>
  </div>;
}
