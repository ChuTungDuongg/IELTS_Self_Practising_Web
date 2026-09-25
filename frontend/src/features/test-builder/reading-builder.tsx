"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertIcon, PlusIcon, ReadingIcon } from "@/components/ui/icons";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import {
  createPassage,
  createQuestionGroup,
  createReadingModule,
  deletePassage,
  deleteModule,
  deleteQuestionGroup,
  reorderQuestionGroups,
  updatePassage,
  updateQuestionGroup,
  type BuilderPassage,
  type BuilderQuestionGroup,
  type BuilderVersion,
  type TextBlock,
} from "@/lib/api/builder";
import { builderPreviewPath } from "@/lib/routes";
import { questionRegistry, readingQuestionTypeOptions } from "@/features/questions/registry";
import type { QuestionGroupModel, QuestionType } from "@/features/questions/types";
import { groupQuestionCount, groupQuestionRange, questionNumbers } from "@/features/questions/numbering";
import { QuestionGroupEditor } from "./question-group-editor";
import { resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { useBuilderAutosave, useBuilderLifecycle } from "./builder-lifecycle";
import { AutosaveLink } from "./autosave-link";
import { ModuleDurationEditor } from "./module-duration-editor";

export function ReadingBuilder({ version }: { version: BuilderVersion }) {
  const router = useRouter();
  const { deleting, transitioning, flushAutosaves, runMutation } = useBuilderLifecycle();
  const sourceReading = version.modules.find((item) => item.module_type === "READING");
  const [savedModule, setSavedModule] = useState<BuilderVersion["modules"][number] | null>(null);
  const [savedPassages, setSavedPassages] = useState<Record<string, BuilderPassage>>({});
  const [savedGroups, setSavedGroups] = useState<Record<string, BuilderQuestionGroup>>({});
  const reading = useMemo(() => {
    if (!sourceReading) return undefined;
    const currentModule = savedModule && savedModule.revision > sourceReading.revision ? savedModule : sourceReading;
    return {
      ...currentModule,
      passages: currentModule.passages.map((item) => {
        const savedPassage = savedPassages[item.id];
        const passage = savedPassage && savedPassage.revision > item.revision
          ? { ...savedPassage, question_groups: item.question_groups }
          : item;
        return {
          ...passage,
          question_groups: passage.question_groups.map((group) => {
            const savedGroup = savedGroups[group.id];
            return savedGroup && savedGroup.revision > group.revision ? savedGroup : group;
          }),
        };
      }),
    };
  }, [sourceReading, savedModule, savedPassages, savedGroups]);
  const moduleRevision = useRef(reading?.revision ?? 1);
  const serverModuleRevision = reading?.revision;
  useEffect(() => { if (serverModuleRevision) moduleRevision.current = serverModuleRevision; }, [serverModuleRevision]);
  const [editingPassage, setEditingPassage] = useState<BuilderPassage | "new" | null>(null);
  const [editingGroup, setEditingGroup] = useState<{ passageId: string; group: QuestionGroupModel } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [confirmingModuleDelete, setConfirmingModuleDelete] = useState(false);
  const nextNumber = useMemo(() => Math.max(0, ...(reading?.passages.flatMap((passage) => passage.question_groups.flatMap(questionNumbers)) ?? [])) + 1, [reading]);
  const nextGroupOrder = useMemo(() => Math.max(-1, ...(reading?.passages.flatMap((passage) => passage.question_groups.map((group) => group.order_index)) ?? [])) + 1, [reading]);
  const duplicateQuestionNumbers = useMemo(() => {
    const numbers = reading?.passages.flatMap((passage) => passage.question_groups.flatMap(questionNumbers)) ?? [];
    return [...new Set(numbers.filter((number, index) => numbers.indexOf(number) !== index))].sort((a, b) => a - b);
  }, [reading]);

  function moveGroup(passageId: string, groupId: string, offset: number) {
    if (!reading) return;
    const passage = reading.passages.find((item) => item.id === passageId);
    if (!passage) return;
    const passageGroups = [...passage.question_groups].sort((a, b) => a.order_index - b.order_index);
    const index = passageGroups.findIndex((group) => group.id === groupId);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= passageGroups.length) return;
    [passageGroups[index], passageGroups[target]] = [passageGroups[target], passageGroups[index]];
    const orderedIds = [...reading.passages]
      .sort((a, b) => a.order_index - b.order_index)
      .flatMap((item) => item.id === passageId ? passageGroups : [...item.question_groups].sort((a, b) => a.order_index - b.order_index))
      .map((group) => group.id);
    void run(async () => {
      const saved = await reorderQuestionGroups(reading.id, orderedIds, moduleRevision.current);
      moduleRevision.current = saved.revision;
      setSavedModule(saved);
    });
  }

  async function run(action: () => Promise<unknown>, excludeAutosaveKey?: string) {
    if (conflict) return;
    setMessage(null);
    try {
      if (!(await flushAutosaves(excludeAutosaveKey))) {
        setMessage("Resolve unsaved draft changes before continuing.");
        return;
      }
      await runMutation(action);
      setEditingPassage(null);
      setEditingGroup(null);
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code === "DRAFT_REVISION_CONFLICT") setConflict(true);
      setMessage(error instanceof ApiError ? error.message : "The builder change could not be saved.");
    }
  }

  async function editPassage(passage: BuilderPassage | "new") {
    if (!(await flushAutosaves())) {
      setMessage("Resolve unsaved draft changes before switching editors.");
      return;
    }
    setEditingPassage(passage);
  }

  async function editGroup(passageId: string, group: QuestionGroupModel) {
    if (!(await flushAutosaves())) {
      setMessage("Resolve unsaved draft changes before switching groups.");
      return;
    }
    setEditingGroup({ passageId, group });
  }

  if (!reading) {
    return (
      <fieldset disabled={deleting || transitioning} className="contents">
        <section aria-busy={deleting} className="reading-empty">
          <div className="empty-state-icon"><ReadingIcon className="size-6" /></div>
          <h2>Build the Reading module</h2>
          <p>Create the module before adding passages, structured question groups, and inline answer keys.</p>
          <button onClick={() => run(() => createReadingModule(version.id))} className="btn btn-primary mt-5"><PlusIcon className="size-4" /> Create Reading module</button>
          {message ? <p role="alert" className="notice notice-error mt-4">{message}</p> : null}
        </section>
      </fieldset>
    );
  }

  return (
    <fieldset disabled={deleting || transitioning} className="contents">
      <section aria-busy={deleting} className="reading-builder">
        <div className="section-header reading-builder-header">
          <div>
            <p className="page-eyebrow">Reading module</p>
            <h2>Reading Builder</h2>
            <p>Build passage blocks, arrange question groups, and keep answer keys next to each question.</p>
          </div>
          <div className="flex flex-wrap gap-2"><AutosaveLink href={builderPreviewPath(version.test_id, version.id, "reading")} className="btn btn-secondary">Preview Reading</AutosaveLink><button onClick={() => void editPassage("new")} className="btn btn-primary"><PlusIcon className="size-4" /> Add passage</button><button onClick={() => setConfirmingModuleDelete(true)} className="btn btn-danger-ghost">Delete module</button></div>
        </div>

        <ModuleDurationEditor module={reading} onPersisted={(saved) => { moduleRevision.current = saved.revision; setSavedModule(saved); }} />
        {duplicateQuestionNumbers.length ? <p role="alert" className="notice notice-error mt-4"><AlertIcon className="mt-0.5 size-4 shrink-0" /> Duplicate displayed question numbers: {duplicateQuestionNumbers.join(", ")}. Renumber before publishing.</p> : null}
        {message ? <p role="alert" className="notice notice-error mt-4"><AlertIcon className="mt-0.5 size-4 shrink-0" /> {message}</p> : null}
        {conflict ? <button type="button" className="btn btn-secondary mt-2" onClick={() => window.location.reload()}>Reload latest</button> : null}

        {editingPassage ? (
          <PassageEditor
            key={editingPassage === "new" ? "new-reading-passage" : editingPassage.id}
            passage={editingPassage === "new" ? undefined : editingPassage}
            orderIndex={reading.passages.length}
            onCancel={() => setEditingPassage(null)}
            onSave={(body) => run(() => createPassage(version.id, body), "passage:new")}
            onAutosave={editingPassage === "new" ? undefined : (body) => updatePassage(editingPassage.id, body)}
            onPersisted={(saved) => { setSavedPassages((current) => ({ ...current, [saved.id]: saved })); setEditingPassage(saved); router.refresh(); }}
          />
        ) : null}

        <div className="passage-list">
          {reading.passages.map((passage) => (
            <article key={passage.id} className="passage-card">
              <div className="passage-card-header">
                <div className="passage-number" aria-hidden="true">{passage.order_index + 1}</div>
                <div className="min-w-0 flex-1">
                  <p className="passage-kicker">Reading passage {passage.order_index + 1}</p>
                  <h3>{passage.title}</h3>
                  <div className="passage-meta">
                    <span>{passage.blocks.filter((block) => block.type === "paragraph").length} paragraphs</span>
                    <span>{passage.question_groups.length} question groups</span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={() => void editPassage(passage)} className="btn btn-secondary">Edit passage</button>
                  <button onClick={() => run(() => deletePassage(passage.id))} className="btn btn-danger-ghost">Delete</button>
                </div>
              </div>

              <div className="question-group-list">
                {passage.question_groups.map((group) => (
                  <GroupSummary key={group.id} group={group} passageNumber={passage.order_index + 1} onMove={(offset) => moveGroup(passage.id, group.id, offset)} onEdit={() => void editGroup(passage.id, group)} onDelete={() => run(() => deleteQuestionGroup(group.id))} />
                ))}
                {editingGroup?.passageId === passage.id ? (
                  <QuestionGroupEditor key={editingGroup.group.id ?? editingGroup.group.questions[0]?.id ?? "new-reading-group"} initial={editingGroup.group} moduleType="READING" nextQuestionNumber={nextNumber} baseQuestionNumber={canonicalReadingGroupStart(reading.passages, editingGroup.group)} passageBlocks={passage.blocks} passageNumber={passage.order_index + 1} testVersionId={version.id} onCancel={() => setEditingGroup(null)} onSave={(body) => run(() => createQuestionGroup(passage.id, body), "question-group:new")} onAutosave={editingGroup.group.id ? (body, expectedRevision) => updateQuestionGroup(editingGroup.group.id!, body, expectedRevision) : undefined} onPersisted={(saved) => { setSavedGroups((current) => ({ ...current, [saved.id]: saved })); setEditingGroup((current) => current?.group.id === saved.id ? { ...current, group: saved } : current); router.refresh(); }} />
                ) : (
                  <NewGroupButton nextNumber={nextNumber} orderIndex={nextGroupOrder} passageBlocks={passage.blocks} onCreate={(group) => void editGroup(passage.id, group)} />
                )}
              </div>
            </article>
          ))}
          {!reading.passages.length ? <div className="reading-inline-empty"><p>No passages yet.</p><span>Add a passage to begin authoring Reading content.</span></div> : null}
        </div>
      </section>
      <ConfirmDialog open={confirmingModuleDelete} title="Delete Reading module?" description="All Reading passages and questions in this draft will be removed." confirmLabel="Delete Reading module" pending={deleting} onCancel={() => setConfirmingModuleDelete(false)} onConfirm={() => void run(() => deleteModule(reading.id))} />
    </fieldset>
  );
}

function PassageEditor({ passage, orderIndex, onSave, onAutosave, onPersisted, onCancel }: { passage?: BuilderPassage; orderIndex: number; onSave: (body: { title: string; order_index: number; blocks: TextBlock[] }) => Promise<void>; onAutosave?: (body: { expected_revision: number; title: string; order_index: number; blocks: TextBlock[] }) => Promise<BuilderPassage>; onPersisted?: (passage: BuilderPassage) => void; onCancel: () => void }) {
  const [title, setTitle] = useState(passage?.title ?? "New reading passage");
  const [blocks, setBlocks] = useState<TextBlock[]>(passage?.blocks ?? [{ id: crypto.randomUUID(), type: "paragraph", label: "A", text: "Passage paragraph" }]);
  const [deletedReferences, setDeletedReferences] = useState<number[]>([]);
  const [pending, setPending] = useState(false);
  const duplicateLabels = duplicateValues(blocks.filter((block) => block.type === "paragraph").map((block) => block.label ?? ""));
  const invalid = !title || !blocks.length || blocks.some((item) => !item.text || (item.type === "paragraph" && !item.label)) || duplicateLabels.length > 0;
  const payload = { title, order_index: passage?.order_index ?? orderIndex, blocks };
  const revision = useRef(passage?.revision ?? 1);
  const { markSaved, saveNow } = useBuilderAutosave({ resourceKey: `passage:${passage?.id ?? "new"}`, value: payload, save: async (value) => {
    if (!onAutosave) { await onSave(value); return; }
    const saved = await onAutosave({ ...value, expected_revision: revision.current });
    revision.current = saved.revision;
    return saved;
  }, onSaved: (saved, _submitted, unchanged) => {
    if (!saved) return;
    onPersisted?.(saved);
    if (unchanged) {
      setTitle(saved.title);
      setBlocks(saved.blocks);
      return { title: saved.title, order_index: saved.order_index, blocks: saved.blocks };
    }
  }, valid: !invalid, enabled: Boolean(passage && onAutosave) });

  function updateBlock(id: string, patch: Partial<TextBlock>) {
    setBlocks(blocks.map((block) => block.id === id ? { ...block, ...patch } : block));
  }

  function moveBlock(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= blocks.length) return;
    const next = [...blocks];
    [next[index], next[target]] = [next[target], next[index]];
    setBlocks(next);
  }

  function removeBlock(id: string) {
    const references = passage?.question_groups.flatMap((group) => group.question_type === "matching_headings" ? group.questions.filter((question) => question.config.target_block_id === id).map((question) => question.number) : group.question_type === "matching_information" ? group.questions.filter((question) => question.answer_key.value === id).map((question) => question.number) : []) ?? [];
    setDeletedReferences((current) => [...new Set([...current, ...references])]);
    setBlocks(blocks.filter((block) => block.id !== id));
  }

  return (
    <fieldset className="passage-editor" disabled={pending} aria-busy={pending}>
      <div className="section-header">
        <div><p className="page-eyebrow">{passage ? "Edit passage" : "New passage"}</p><h3>{passage ? passage.title : "Create a reading passage"}</h3></div>
      </div>
      <label className="field-label mt-5">Passage title<input value={title} onChange={(event) => setTitle(event.target.value)} className="field" /></label>
      {duplicateLabels.length ? <p role="alert" className="notice notice-error mt-3">Duplicate paragraph labels: {duplicateLabels.join(", ")}.</p> : null}
      {deletedReferences.length ? <p role="alert" className="notice notice-error mt-3">Deleted paragraphs were referenced by Q{deletedReferences.join(", Q")}. Those assignments will be marked invalid until repaired.</p> : null}

      <div className="block-list">
        {blocks.map((block, index) => (
          <div key={block.id} className={`content-block ${block.type === "heading" ? "subheading-block" : "paragraph-block"}`}>
            <div className="content-block-side">
              {block.type === "paragraph" ? <span className="block-label">{block.label || "?"}</span> : <span className="subheading-mark">H</span>}
              <div className="block-move-actions">
                <button type="button" onClick={() => moveBlock(index, -1)} aria-label="Move block up">↑</button>
                <button type="button" onClick={() => moveBlock(index, 1)} aria-label="Move block down">↓</button>
              </div>
            </div>
            <div className="content-block-main">
              <div className="content-block-toolbar">
                <label className="field-label">Block type<select value={block.type} onChange={(event) => updateBlock(block.id, { type: event.target.value as TextBlock["type"], label: event.target.value === "paragraph" ? (block.label ?? nextParagraphLabel(blocks)) : null })} className="select-field"><option value="paragraph">Paragraph</option><option value="heading">Subheading</option></select></label>
                {block.type === "paragraph" ? <label className="field-label w-24">Paragraph label<input aria-label={`Paragraph ${index + 1} label`} value={block.label ?? ""} onChange={(event) => updateBlock(block.id, { label: event.target.value })} className="field" /></label> : null}
                <button type="button" onClick={() => removeBlock(block.id)} className="btn btn-danger-ghost ml-auto">Remove</button>
              </div>
              <label className="field-label mt-3">{block.type === "paragraph" ? `Paragraph ${block.label || ""} text` : "Subheading text"}<textarea aria-label={`Block ${index + 1} text`} value={block.text} onChange={(event) => updateBlock(block.id, { text: event.target.value })} rows={block.type === "paragraph" ? 5 : 2} className="field resize-y" /></label>
            </div>
          </div>
        ))}
      </div>

      <div className="passage-editor-footer">
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setBlocks([...blocks, { id: crypto.randomUUID(), type: "paragraph", label: nextParagraphLabel(blocks), text: "New paragraph" }])} className="btn btn-secondary"><PlusIcon className="size-4" /> Add paragraph</button>
          <button type="button" onClick={() => setBlocks([...blocks, { id: crypto.randomUUID(), type: "heading", label: null, text: "New subheading" }])} className="btn btn-secondary"><PlusIcon className="size-4" /> Add subheading</button>
        </div>
        <div className="flex gap-2"><button type="button" onClick={() => { if (passage) void saveNow().then((saved) => { if (saved) onCancel(); }); else onCancel(); }} className="btn btn-ghost">{passage ? "Close" : "Cancel"}</button><button type="button" disabled={invalid || pending} onClick={async () => { setPending(true); try { if (passage) await saveNow(); else { await onSave(payload); markSaved(); } } finally { setPending(false); } }} className="btn btn-primary">{pending ? "Saving…" : passage ? "Save now" : "Create passage"}</button></div>
      </div>
    </fieldset>
  );
}

function GroupSummary({ group, passageNumber, onMove, onEdit, onDelete }: { group: BuilderQuestionGroup; passageNumber: number; onMove: (offset: number) => void; onEdit: () => void; onDelete: () => void }) {
  const range = groupQuestionRange(group);
  return (
    <div className="question-group-card">
      <span className="question-range">{range}</span>
      <div className="min-w-0 flex-1"><p>{questionRegistry[group.question_type].label}</p><span>{groupQuestionCount(group)} question{groupQuestionCount(group) === 1 ? "" : "s"} · {resolveQuestionGroupInstruction(group, { passageNumber }).intro}</span></div>
      <div className="group-actions"><button type="button" onClick={() => onMove(-1)} aria-label="Move question group up" className="icon-button">↑</button><button type="button" onClick={() => onMove(1)} aria-label="Move question group down" className="icon-button">↓</button><button onClick={onEdit} className="btn btn-secondary">Edit / Preview</button><button onClick={onDelete} className="btn btn-danger-ghost">Delete</button></div>
    </div>
  );
}

function NewGroupButton({ nextNumber, orderIndex, passageBlocks, onCreate }: { nextNumber: number; orderIndex: number; passageBlocks: TextBlock[]; onCreate: (group: QuestionGroupModel) => void }) {
  const [type, setType] = useState<QuestionType>("multiple_choice");
  function create() {
    const group = { ...questionRegistry[type].createDefault(nextNumber, { moduleType: "READING" }), order_index: orderIndex };
    if (type === "matching_headings") group.questions[0].config = { target_block_id: passageBlocks.find((block) => block.type === "paragraph")?.id ?? "" };
    onCreate(group);
  }
  return <div className="new-group-row"><label className="field-label flex-1">Question type<select value={type} onChange={(event) => setType(event.target.value as QuestionType)} className="select-field">{readingQuestionTypeOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><button onClick={create} className="btn btn-secondary"><PlusIcon className="size-4" /> Add question group</button></div>;
}

function duplicateValues(values: string[]): string[] {
  const normalized = values.map((value) => value.trim().toLocaleLowerCase());
  return values.filter((_, index) => normalized[index] && normalized.indexOf(normalized[index]) !== index);
}

function nextParagraphLabel(blocks: TextBlock[]): string {
  const count = blocks.filter((block) => block.type === "paragraph").length;
  let value = count + 1;
  let label = "";
  while (value) {
    value--;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}

function canonicalReadingGroupStart(passages: BuilderPassage[], target: QuestionGroupModel): number {
  let number = 1;
  for (const passage of [...passages].sort((a, b) => a.order_index - b.order_index)) {
    for (const group of [...passage.question_groups].sort((a, b) => a.order_index - b.order_index)) {
      if (group.id === target.id) return target.questions.length ? Math.min(...target.questions.map((question) => question.number)) : number;
      number += groupQuestionCount(group);
    }
  }
  return target.questions.length ? Math.min(...target.questions.map((question) => question.number)) : number;
}
