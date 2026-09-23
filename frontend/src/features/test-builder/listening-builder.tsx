"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon } from "@/components/ui/icons";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { listeningQuestionTypeOptions, questionRegistry } from "@/features/questions/registry";
import type { QuestionGroupModel, QuestionType } from "@/features/questions/types";
import { uploadAsset } from "@/lib/api/assets";
import {
  attachListeningAudio,
  createListeningModule,
  createListeningPart,
  createListeningQuestionGroup,
  deleteQuestionGroup,
  deleteModule,
  reorderQuestionGroups,
  updateListeningPart,
  updateListeningQuestionGroup,
  type BuilderVersion,
} from "@/lib/api/builder";
import { builderPreviewPath } from "@/lib/routes";
import { ApiError } from "@/lib/api/client";
import { useBuilderAutosave, useBuilderLifecycle } from "./builder-lifecycle";
import { AutosaveLink } from "./autosave-link";
import { QuestionGroupEditor } from "./question-group-editor";

export function ListeningBuilder({ version }: { version: BuilderVersion }) {
  const router = useRouter();
  const { deleting, transitioning, flushAutosaves, runMutation } = useBuilderLifecycle();
  const listening = version.modules.find((item) => item.module_type === "LISTENING");
  const parts = useMemo(() => [...(listening?.listening_parts ?? [])].sort((a, b) => a.order_index - b.order_index), [listening]);
  const [partIndex, setPartIndex] = useState(0);
  const [editing, setEditing] = useState<QuestionGroupModel | null>(null);
  const [type, setType] = useState<QuestionType>("multiple_choice");
  const [message, setMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmingModuleDelete, setConfirmingModuleDelete] = useState(false);
  const part = parts[partIndex];
  const nextNumber = Math.max(0, ...parts.flatMap((item) => item.question_groups.flatMap((group) => group.questions.map((question) => question.number)))) + 1;
  const nextOrder = Math.max(-1, ...parts.flatMap((item) => item.question_groups.map((group) => group.order_index))) + 1;

  async function run(action: () => Promise<unknown>, excludeAutosaveKey?: string) {
    setMessage(null);
    try {
      if (!(await flushAutosaves(excludeAutosaveKey))) {
        setMessage("Fix invalid draft fields or retry the failed save before continuing.");
        return;
      }
      await runMutation(action);
      setEditing(null);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The Listening change could not be saved.");
    }
  }

  async function initialize() {
    await run(async () => {
      if (!listening) await createListeningModule(version.id);
      const existingIndexes = new Set(parts.map((item) => item.order_index));
      for (let index = 0; index < 4; index++) {
        if (!existingIndexes.has(index)) await createListeningPart(version.id, { title: `Section ${index + 1}`, order_index: index });
      }
    });
  }

  async function uploadAudio(file: File) {
    if (!listening) return;
    setUploading(true);
    try {
      const asset = await uploadAsset("audio", version.id, file);
      await run(() => attachListeningAudio(listening.id, asset.id));
    } finally {
      setUploading(false);
    }
  }

  if (!listening || parts.length < 4) {
    return (
      <fieldset disabled={deleting || transitioning} className="contents"><section className="reading-empty listening-empty">
        <div className="listening-orb" />
        <h2>{listening ? "Complete the four-section structure" : "Build the Listening module"}</h2>
        <p>Create stable Section 1–4 records. Shared audio is optional and can be attached later.</p>
        <button disabled={deleting} onClick={initialize} className="btn btn-listening mt-5"><PlusIcon className="size-4" /> {listening ? "Add missing sections" : "Create Listening module"}</button>
        {message ? <p className="notice notice-error mt-4">{message}</p> : null}
      </section></fieldset>
    );
  }

  function createGroup() {
    setEditing({ ...questionRegistry[type].createDefault(nextNumber, { moduleType: "LISTENING" }), order_index: nextOrder });
  }

  async function switchPart(index: number) {
    if (!(await flushAutosaves())) {
      setMessage("Fix invalid draft fields or retry the failed save before switching sections.");
      return;
    }
    setPartIndex(index);
    setEditing(null);
  }

  async function editGroup(group: QuestionGroupModel) {
    if (!(await flushAutosaves())) {
      setMessage("Fix invalid draft fields or retry the failed save before switching groups.");
      return;
    }
    setEditing(group);
  }

  function moveGroup(groupId: string, offset: number) {
    if (!listening || !part) return;
    const local = [...part.question_groups].sort((a, b) => a.order_index - b.order_index);
    const index = local.findIndex((item) => item.id === groupId);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= local.length) return;
    [local[index], local[target]] = [local[target], local[index]];
    const ids = parts.flatMap((item) => item.id === part.id ? local : [...item.question_groups].sort((a, b) => a.order_index - b.order_index)).map((item) => item.id);
    void run(() => reorderQuestionGroups(listening.id, ids));
  }

  return (
    <fieldset disabled={deleting || transitioning} className="contents">
      <section className="listening-builder">
        <div className="section-header">
          <div><p className="page-eyebrow listening-eyebrow">Listening module</p><h2>Listening Builder</h2><p>Four stable sections, globally numbered questions, and one optional shared recording.</p></div>
          <div className="flex flex-wrap gap-2"><AutosaveLink href={builderPreviewPath(version.test_id, version.id, "listening")} className="btn btn-secondary">Preview Listening</AutosaveLink><span className="module-state">{parts.flatMap((item) => item.question_groups.flatMap((group) => group.questions)).length} / 40 questions</span><button onClick={() => setConfirmingModuleDelete(true)} className="btn btn-danger-ghost">Delete module</button></div>
        </div>

        <div className="listening-part-tabs" role="tablist">
          {parts.map((item, index) => <button key={item.id} role="tab" aria-selected={index === partIndex} onClick={() => void switchPart(index)} className={index === partIndex ? "active" : ""}><b>Section {item.order_index + 1}</b><span>{item.question_groups.flatMap((group) => group.questions).length} questions</span></button>)}
        </div>

        {message ? <p className="notice notice-error mt-4">{message}</p> : null}
        <div className="audio-attachment mt-5">
          <div><p className="page-eyebrow">Shared Listening audio</p><h3>{listening.audio_asset?.original_name ?? "No recording attached"}</h3><span>{listening.audio_asset ? `${(listening.audio_asset.file_size / 1024 / 1024).toFixed(1)} MB · ${listening.audio_asset.mime_type}` : "Optional · used by all four sections"}</span></div>
          <div className="flex flex-wrap gap-2">
            <label className="btn btn-listening">{uploading ? "Uploading…" : listening.audio_asset ? "Replace" : "Upload audio"}<input type="file" className="sr-only" accept="audio/mpeg,audio/mp4,audio/x-m4a,audio/aac,audio/wav,audio/ogg" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadAudio(file); }} /></label>
            {listening.audio_asset ? <button className="btn btn-danger-ghost" onClick={() => run(() => attachListeningAudio(listening.id, null))}>Remove</button> : null}
          </div>
        </div>

        {part ? (
          <div className="listening-part-panel">
            <ListeningPartTitle key={part.id} part={part} />
            <div className="question-group-list mt-5">
              {part.question_groups.map((group) => {
                const numbers = group.questions.map((item) => item.number);
                return <div key={group.id} className="question-group-card listening-group-card"><span className="question-range">{numbers.length ? `Q${Math.min(...numbers)}–${Math.max(...numbers)}` : "—"}</span><div className="min-w-0 flex-1"><p>{questionRegistry[group.question_type].label}</p><span>{resolveQuestionGroupInstruction(group).intro}</span></div><div className="group-actions"><button className="icon-button" onClick={() => moveGroup(group.id, -1)}>↑</button><button className="icon-button" onClick={() => moveGroup(group.id, 1)}>↓</button><button className="btn btn-secondary" onClick={() => void editGroup(group)}>Edit</button><button className="btn btn-danger-ghost" onClick={() => run(() => deleteQuestionGroup(group.id))}>Delete</button></div></div>;
              })}
              {editing ? (
                <div>
                  <QuestionGroupEditor key={editing.id ?? editing.questions[0]?.id ?? "new-listening-group"} initial={editing} moduleType="LISTENING" nextQuestionNumber={nextNumber} baseQuestionNumber={canonicalListeningGroupStart(parts, editing)} passageBlocks={[]} testVersionId={version.id} onCancel={() => setEditing(null)} onSave={(body) => run(() => editing.id ? updateListeningQuestionGroup(editing.id, body) : createListeningQuestionGroup(part.id, body), editing.id ? undefined : "question-group:new")} onAutosave={editing.id ? (body) => updateListeningQuestionGroup(editing.id!, body) : undefined} />
                </div>
              ) : (
                <div className="new-group-row"><label className="field-label flex-1">Listening template<select className="select-field" value={type} onChange={(event) => setType(event.target.value as QuestionType)}>{listeningQuestionTypeOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><button className="btn btn-listening" onClick={createGroup}><PlusIcon className="size-4" /> Add question group</button></div>
              )}
            </div>
          </div>
        ) : null}
      </section>
      <ConfirmDialog open={confirmingModuleDelete} title="Delete Listening module?" description="All Listening sections and questions in this draft will be removed." confirmLabel="Delete Listening module" pending={deleting} onCancel={() => setConfirmingModuleDelete(false)} onConfirm={() => void run(() => deleteModule(listening.id))} />
    </fieldset>
  );
}

function ListeningPartTitle({ part }: { part: { id: string; title: string | null; order_index: number } }) {
  const [title, setTitle] = useState(part.title ?? `Section ${part.order_index + 1}`);
  useBuilderAutosave({ resourceKey: `listening-part:${part.id}`, value: { title, order_index: part.order_index }, save: (value) => updateListeningPart(part.id, value), valid: title.trim().length > 0 && title.length <= 240 });
  return <label className="field-label mb-4 block">Section title / internal label<input className="field mt-2" value={title} onChange={(event) => setTitle(event.target.value)} /></label>;
}

function canonicalListeningGroupStart(
  parts: Array<{ order_index: number; question_groups: QuestionGroupModel[] }>,
  target: QuestionGroupModel,
): number {
  let number = 1;
  for (const part of [...parts].sort((a, b) => a.order_index - b.order_index)) {
    for (const group of [...part.question_groups].sort((a, b) => a.order_index - b.order_index)) {
      if (group.id === target.id) return number;
      number += group.questions.length;
    }
  }
  return target.questions.length ? Math.min(...target.questions.map((question) => question.number)) : number;
}
