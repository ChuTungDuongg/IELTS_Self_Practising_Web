"use client";

import { useState } from "react";
import Link from "next/link";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { ListeningAudioPlayer } from "@/features/listening/audio-player";
import { assetContentUrl } from "@/lib/api/assets";
import type { BuilderListeningPart, BuilderPassage, BuilderVersion } from "@/lib/api/builder";
import { builderEditPath } from "@/lib/routes";

export function DraftPreview({ version, moduleType }: { version: BuilderVersion; moduleType: "READING" | "LISTENING" }) {
  const builderModule = version.modules.find((item) => item.module_type === moduleType);
  const sections: Array<BuilderPassage | BuilderListeningPart> = moduleType === "READING" ? builderModule?.passages ?? [] : builderModule?.listening_parts ?? [];
  const [sectionIndex, setSectionIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const section = sections[sectionIndex];
  if (!builderModule || !section) return <p className="notice notice-error">This draft module has no previewable content yet.</p>;
  const passage = moduleType === "READING" ? section as BuilderPassage : null;
  const groups = section.question_groups;
  return <div className={`exam-runner draft-preview ${moduleType === "LISTENING" ? "listening-exam" : ""}`}>
    <header className="exam-header"><div><p>DRAFT PREVIEW · {moduleType}</p><h1>{version.test_title}</h1></div><Link className="btn btn-secondary" href={`${builderEditPath(version.test_id, version.id)}?workspace=${moduleType.toLowerCase()}`}>Back to Builder</Link></header>
    {moduleType === "LISTENING" ? builderModule.audio_asset ? <ListeningAudioPlayer src={assetContentUrl(builderModule.audio_asset)} /> : <p className="notice m-4">No audio is attached. Preview remains available.</p> : null}
    <main className={moduleType === "READING" ? "grid min-h-0 flex-1 lg:grid-cols-2" : "listening-question-pane"}>
      {passage ? <article className="exam-passage"><div className="exam-passage-content"><p className="exam-passage-kicker">Reading passage {passage.order_index + 1}</p><h2>{passage.title}</h2><div className="exam-passage-body">{passage.blocks.map((block) => block.type === "heading" ? <h3 key={block.id}>{block.text}</h3> : <p key={block.id} className="exam-passage-paragraph"><b>{block.label}</b>{block.text}</p>)}</div></div></article> : null}
      <div className="exam-questions"><div className="exam-question-panel-heading"><p>{moduleType === "READING" ? `Reading · Passage ${section.order_index + 1}` : `${moduleType} · Section ${section.order_index + 1}`}</p><h2>{moduleType === "READING" ? "Questions" : section.title}</h2></div>{groups.map((group) => { const definition = questionRegistry[group.question_type]; if (!definition) return <p key={group.id} role="alert">Unsupported question type: {group.question_type}</p>; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} passageNumber={moduleType === "READING" ? section.order_index + 1 : undefined} /><Renderer group={group as ExamGroup} values={values} passageBlocks={passage?.blocks ?? []} onAnswer={(id, value) => setValues((current) => ({ ...current, [id]: value }))} /></section>; })}</div>
    </main>
    <footer className="exam-footer"><div className="exam-footer-navigation"><nav className="exam-passage-navigation" aria-label={`${moduleType === "READING" ? "Passage" : "Section"} navigation`}>{sections.map((item, index) => <button key={item.id} onClick={() => setSectionIndex(index)} className={index === sectionIndex ? "active" : ""}>{moduleType === "READING" ? "Passage" : "Section"} {item.order_index + 1}</button>)}</nav></div><span className="exam-preview-note">Answers in preview are not saved.</span></footer>
  </div>;
}
