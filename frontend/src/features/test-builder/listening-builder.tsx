"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon } from "@/components/ui/icons";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { listeningQuestionTypeOptions, questionRegistry } from "@/features/questions/registry";
import type { QuestionGroupModel, QuestionType } from "@/features/questions/types";
import { groupQuestionCount, groupQuestionRange, questionNumbers } from "@/features/questions/numbering";
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
  type BuilderListeningPart,
  type BuilderQuestionGroup,
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
  const sourceListening = version.modules.find((item) => item.module_type === "LISTENING");
  const [savedModule, setSavedModule] = useState<BuilderVersion["modules"][number] | null>(null);
  const [savedParts, setSavedParts] = useState<Record<string, BuilderListeningPart>>({});
  const [savedGroups, setSavedGroups] = useState<Record<string, BuilderQuestionGroup>>({});
  const listening = useMemo(() => {
    if (!sourceListening) return undefined;
    const currentModule = savedModule && savedModule.revision > sourceListening.revision ? savedModule : sourceListening;
    return {
      ...currentModule,
      listening_parts: currentModule.listening_parts.map((item) => {
        const savedPart = savedParts[item.id];
        const part = savedPart && savedPart.revision > item.revision
          ? { ...savedPart, question_groups: item.question_groups }
          : item;
        return {
          ...part,
          question_groups: part.question_groups.map((group) => {
            const savedGroup = savedGroups[group.id];
            return savedGroup && savedGroup.revision > group.revision ? savedGroup : group;
          }),
        };
      }),
    };
  }, [sourceListening, savedModule, savedParts, savedGroups]);
  const moduleRevision = useRef(listening?.revision ?? 1);
  const serverModuleRevision = listening?.revision;
  useEffect(() => { if (serverModuleRevision) moduleRevision.current = serverModuleRevision; }, [serverModuleRevision]);
  const parts = useMemo(() => [...(listening?.listening_parts ?? [])].sort((a, b) => a.order_index - b.order_index), [listening]);
  const [partIndex, setPartIndex] = useState(0);
  const [editing, setEditing] = useState<QuestionGroupModel | null>(null);
  const [type, setType] = useState<QuestionType>("multiple_choice");
  const [message, setMessage] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [confirmingModuleDelete, setConfirmingModuleDelete] = useState(false);
  const part = parts[partIndex];
  const nextNumber = Math.max(0, ...parts.flatMap((item) => item.question_groups.flatMap(questionNumbers))) + 1;
  const nextOrder = Math.max(-1, ...parts.flatMap((item) => item.question_groups.map((group) => group.order_index))) + 1;

  async function run(action: () => Promise<unknown>, excludeAutosaveKey?: string) {
    if (conflict) return;
    setMessage(null);
    try {
      if (!(await flushAutosaves(excludeAutosaveKey))) {
        setMessage("Resolve unsaved draft changes before continuing.");
        return;
      }
      await runMutation(action);
      setEditing(null);
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code === "DRAFT_REVISION_CONFLICT") setConflict(true);
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
      await run(async () => {
        const saved = await attachListeningAudio(listening.id, asset.id, moduleRevision.current);
        moduleRevision.current = saved.revision;
        setSavedModule(saved);
      });
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
      setMessage("Resolve unsaved draft changes before switching sections.");
      return;
    }
    setPartIndex(index);
    setEditing(null);
  }

  async function editGroup(group: QuestionGroupModel) {
    if (!(await flushAutosaves())) {
      setMessage("Resolve unsaved draft changes before switching groups.");
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
    void run(async () => {
      const saved = await reorderQuestionGroups(listening.id, ids, moduleRevision.current);
      moduleRevision.current = saved.revision;
      setSavedModule(saved);
    });
  }

  return (
    <fieldset disabled={deleting || transitioning} className="contents">
      <section className="listening-builder">
        <div className="section-header">
          <div><p className="page-eyebrow listening-eyebrow">Listening module</p><h2>Listening Builder</h2><p>Four stable sections, globally numbered questions, and one optional shared recording.</p></div>
          <div className="flex flex-wrap gap-2"><AutosaveLink href={builderPreviewPath(version.test_id, version.id, "listening")} className="btn btn-secondary">Preview Listening</AutosaveLink><span className="module-state">{parts.reduce((total, item) => total + item.question_groups.reduce((count, group) => count + groupQuestionCount(group), 0), 0)} / 40 questions</span><button onClick={() => setConfirmingModuleDelete(true)} className="btn btn-danger-ghost">Delete module</button></div>
        </div>

        <div className="listening-part-tabs" role="tablist">
          {parts.map((item, index) => <button key={item.id} role="tab" aria-selected={index === partIndex} onClick={() => void switchPart(index)} className={index === partIndex ? "active" : ""}><b>Section {item.order_index + 1}</b><span>{item.question_groups.reduce((count, group) => count + groupQuestionCount(group), 0)} questions</span></button>)}
        </div>

        {message ? <p className="notice notice-error mt-4">{message}</p> : null}
        {conflict ? <button type="button" className="btn btn-secondary mt-2" onClick={() => window.location.reload()}>Reload latest</button> : null}
        <div className="audio-attachment mt-5">
          <div><p className="page-eyebrow">Shared Listening audio</p><h3>{listening.audio_asset?.original_name ?? "No recording attached"}</h3><span>{listening.audio_asset ? `${(listening.audio_asset.file_size / 1024 / 1024).toFixed(1)} MB · ${listening.audio_asset.mime_type}` : "Optional · used by all four sections"}</span></div>
          <div className="flex flex-wrap gap-2">
            <label className="btn btn-listening">{uploading ? "Uploading…" : listening.audio_asset ? "Replace" : "Upload audio"}<input type="file" className="sr-only" accept="audio/mpeg,audio/mp4,audio/x-m4a,audio/aac,audio/wav,audio/ogg" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadAudio(file); }} /></label>
            {listening.audio_asset ? <button className="btn btn-danger-ghost" onClick={() => run(async () => { const saved = await attachListeningAudio(listening.id, null, moduleRevision.current); moduleRevision.current = saved.revision; setSavedModule(saved); })}>Remove</button> : null}
          </div>
        </div>

        {part ? (
          <div className="listening-part-panel">
            <ListeningPartTitle key={part.id} part={part} onPersisted={(saved) => { setSavedParts((current) => ({ ...current, [saved.id]: saved })); router.refresh(); }} />
            <div className="question-group-list mt-5">
              {part.question_groups.map((group) => {
                return <div key={group.id} className="question-group-card listening-group-card"><span className="question-range">{groupQuestionRange(group)}</span><div className="min-w-0 flex-1"><p>{questionRegistry[group.question_type].label}</p><span>{resolveQuestionGroupInstruction(group).intro}</span></div><div className="group-actions"><button className="icon-button" onClick={() => moveGroup(group.id, -1)}>↑</button><button className="icon-button" onClick={() => moveGroup(group.id, 1)}>↓</button><button className="btn btn-secondary" onClick={() => void editGroup(group)}>Edit</button><button className="btn btn-danger-ghost" onClick={() => run(() => deleteQuestionGroup(group.id))}>Delete</button></div></div>;
              })}
              {editing ? (
                <div>
                  <QuestionGroupEditor key={editing.id ?? editing.questions[0]?.id ?? "new-listening-group"} initial={editing} moduleType="LISTENING" nextQuestionNumber={nextNumber} baseQuestionNumber={canonicalListeningGroupStart(parts, editing)} passageBlocks={[]} testVersionId={version.id} onCancel={() => setEditing(null)} onSave={(body) => run(() => createListeningQuestionGroup(part.id, body), "question-group:new")} onAutosave={editing.id ? (body, expectedRevision) => updateListeningQuestionGroup(editing.id!, body, expectedRevision) : undefined} onPersisted={(saved) => { setSavedGroups((current) => ({ ...current, [saved.id]: saved })); setEditing(saved); router.refresh(); }} />
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

function ListeningPartTitle({ part, onPersisted }: { part: BuilderListeningPart; onPersisted: (part: BuilderListeningPart) => void }) {
  const [title, setTitle] = useState(part.title ?? `Section ${part.order_index + 1}`);
  const revision = useRef(part.revision);
  useBuilderAutosave({ resourceKey: `listening-part:${part.id}`, value: { title, order_index: part.order_index }, save: async (value) => {
    const saved = await updateListeningPart(part.id, { ...value, expected_revision: revision.current });
    revision.current = saved.revision;
    return saved;
  }, onSaved: (saved, _submitted, unchanged) => {
    onPersisted(saved);
    if (unchanged) {
      const canonical = saved.title ?? `Section ${saved.order_index + 1}`;
      setTitle(canonical);
      return { title: canonical, order_index: saved.order_index };
    }
  }, valid: title.trim().length > 0 && title.length <= 240 });
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
      number += groupQuestionCount(group);
    }
  }
  return target.questions.length ? Math.min(...target.questions.map((question) => question.number)) : number;
}
