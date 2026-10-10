"use client";

import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { useTranslation } from "@/lib/i18n/locale-provider";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { ListeningAudioPlayer } from "@/features/listening/audio-player";
import { assetContentUrl } from "@/lib/api/assets";
import type { BuilderListeningPart, BuilderPassage, BuilderVersion } from "@/lib/api/builder";
import { builderEditPath } from "@/lib/routes";

export function DraftPreview({ version, moduleType }: { version: BuilderVersion; moduleType: "READING" | "LISTENING" | "WRITING" }) {
  const { t } = useTranslation();
  const builderModule = version.modules.find((item) => item.module_type === moduleType);
  const sections: Array<BuilderPassage | BuilderListeningPart> = moduleType === "READING" ? builderModule?.passages ?? [] : moduleType === "LISTENING" ? builderModule?.listening_parts ?? [] : [];
  const [sectionIndex, setSectionIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const section = sections[sectionIndex];
  if (moduleType === "WRITING") {
    const tasks = [...(builderModule?.writing_tasks ?? [])].sort((a, b) => a.order_index - b.order_index);
    if (!builderModule || !tasks.length) return <p className="notice notice-error">{t("runner.noPreview")}</p>;
    return <div className="exam-runner draft-preview writing-exam">
      <header className="exam-header"><div><p>{t("runner.draftPreviewModule", { module: t("common.writing") })}</p><h1>{version.test_title}</h1></div><Link className="btn btn-secondary" href={`${builderEditPath(version.test_id, version.id)}?workspace=writing`}>{t("runner.backBuilder")}</Link></header>
      <main className="writing-preview-layout">
        {tasks.map((task) => <article key={task.id} className="writing-preview-task">
          <p className="writing-task-kicker">{t("runner.writingTask", { number: task.task_number })}</p>
          <h2>{t("common.taskNumber", { number: task.task_number })}</h2>
          <p>{task.prompt || t("runner.noPrompt")}</p>
          {task.image_asset ? <Image unoptimized width={720} height={420} src={assetContentUrl(task.image_asset)} alt={t("runner.writingReference", { number: task.task_number })} /> : null}
          <div className="writing-preview-guidance"><span>{t("runner.wordCount", { count: task.minimum_recommended_words ?? "—" })}</span><span>{t("runner.minutes", { count: task.recommended_duration_seconds ? Math.round(task.recommended_duration_seconds / 60) : "—" })}</span></div>
          <div className="writing-preview-response" aria-label={t("runner.previewTaskResponse", { number: task.task_number })}>{t("runner.candidateResponse")}</div>
        </article>)}
      </main>
      <footer className="exam-footer"><span className="exam-preview-note">{t("runner.previewResponses")}</span></footer>
    </div>;
  }
  if (!builderModule || !section) return <p className="notice notice-error">{t("runner.noPreview")}</p>;
  const passage = moduleType === "READING" ? section as BuilderPassage : null;
  const groups = section.question_groups;
  return <div className={`exam-runner draft-preview ${moduleType === "LISTENING" ? "listening-exam" : ""}`}>
    <header className="exam-header"><div><p>{t("runner.draftPreviewModule", { module: t(moduleTranslationKeys[moduleType]) })}</p><h1>{version.test_title}</h1></div><Link className="btn btn-secondary" href={`${builderEditPath(version.test_id, version.id)}?workspace=${moduleType.toLowerCase()}`}>{t("runner.backBuilder")}</Link></header>
    {moduleType === "LISTENING" ? builderModule.audio_asset ? <ListeningAudioPlayer src={assetContentUrl(builderModule.audio_asset)} /> : <p className="notice m-4">{t("runner.previewNoAudio")}</p> : null}
    <main className={moduleType === "READING" ? "grid min-h-0 flex-1 lg:grid-cols-2" : "listening-question-pane"}>
      {passage ? <article className="exam-passage"><div className="exam-passage-content"><p className="exam-passage-kicker">{t("runner.readingPassageKicker", { number: passage.order_index + 1 })}</p><h2>{passage.title}</h2><div className="exam-passage-body">{passage.blocks.map((block) => block.type === "heading" ? <h3 key={block.id}>{block.text}</h3> : <p key={block.id} className="exam-passage-paragraph"><b>{block.label}</b>{block.text}</p>)}</div></div></article> : null}
      <div className="exam-questions"><div className="exam-question-panel-heading"><p>{moduleType === "READING" ? t("runner.readingPassage", { number: section.order_index + 1 }) : t("runner.moduleSection", { module: t(moduleTranslationKeys[moduleType]), number: section.order_index + 1 })}</p><h2>{moduleType === "READING" ? t("common.questions") : section.title}</h2></div>{groups.map((group) => { const definition = questionRegistry[group.question_type]; if (!definition) return <p key={group.id} role="alert">{t("runner.unsupportedType", { type: group.question_type })}</p>; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} passageNumber={moduleType === "READING" ? section.order_index + 1 : undefined} /><Renderer group={group as ExamGroup} values={values} passageBlocks={passage?.blocks ?? []} onAnswer={(id, value) => setValues((current) => ({ ...current, [id]: value }))} /></section>; })}</div>
    </main>
    <footer className="exam-footer"><div className="exam-footer-navigation"><nav className="exam-passage-navigation" aria-label={t(moduleType === "READING" ? "runner.passageNavigation" : "runner.sectionNavigation")}>{sections.map((item, index) => <button key={item.id} onClick={() => setSectionIndex(index)} className={index === sectionIndex ? "active" : ""}>{t(moduleType === "READING" ? "common.passageNumber" : "common.sectionNumber", { number: item.order_index + 1 })}</button>)}</nav></div><span className="exam-preview-note">{t("runner.previewAnswers")}</span></footer>
  </div>;
}
