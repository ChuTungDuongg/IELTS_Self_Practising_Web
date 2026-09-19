"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { AlertIcon, PlusIcon, ReadingIcon } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import {
  createPassage,
  createQuestionGroup,
  createReadingModule,
  deletePassage,
  deleteQuestionGroup,
  reorderQuestionGroups,
  updatePassage,
  updateQuestionGroup,
  type BuilderPassage,
  type BuilderQuestionGroup,
  type BuilderVersion,
  type TextBlock,
} from "@/lib/api/builder";
import { questionRegistry, readingQuestionTypeOptions } from "@/features/questions/registry";
import type { QuestionGroupModel, QuestionType } from "@/features/questions/types";
import { QuestionGroupEditor } from "./question-group-editor";
import { resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { useBuilderLifecycle } from "./builder-lifecycle";

export function ReadingBuilder({ version }: { version: BuilderVersion }) {
  const router = useRouter();
  const { deleting, runMutation } = useBuilderLifecycle();
  const reading = version.modules.find((item) => item.module_type === "READING");
  const [editingPassage, setEditingPassage] = useState<BuilderPassage | "new" | null>(null);
  const [editingGroup, setEditingGroup] = useState<{ passageId: string; group: QuestionGroupModel } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const nextNumber = useMemo(() => Math.max(0, ...(reading?.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => question.number))) ?? [])) + 1, [reading]);
  const nextGroupOrder = useMemo(() => Math.max(-1, ...(reading?.passages.flatMap((passage) => passage.question_groups.map((group) => group.order_index)) ?? [])) + 1, [reading]);
  const duplicateQuestionNumbers = useMemo(() => {
    const numbers = reading?.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => question.number))) ?? [];
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
    void run(() => reorderQuestionGroups(reading.id, orderedIds));
  }

  async function run(action: () => Promise<unknown>) {
    setMessage(null);
    try {
      await runMutation(action);
      setEditingPassage(null);
      setEditingGroup(null);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The builder change could not be saved.");
    }
  }

  if (!reading) {
    return (
      <fieldset disabled={deleting} className="contents">
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
    <fieldset disabled={deleting} className="contents">
      <section aria-busy={deleting} className="reading-builder">
        <div className="section-header reading-builder-header">
          <div>
            <p className="page-eyebrow">Reading module</p>
            <h2>Reading Builder</h2>
            <p>Build passage blocks, arrange question groups, and keep answer keys next to each question.</p>
          </div>
          <button onClick={() => setEditingPassage("new")} className="btn btn-primary"><PlusIcon className="size-4" /> Add passage</button>
        </div>

        {duplicateQuestionNumbers.length ? <p role="alert" className="notice notice-error mt-4"><AlertIcon className="mt-0.5 size-4 shrink-0" /> Duplicate displayed question numbers: {duplicateQuestionNumbers.join(", ")}. Renumber before publishing.</p> : null}
        {message ? <p role="alert" className="notice notice-error mt-4"><AlertIcon className="mt-0.5 size-4 shrink-0" /> {message}</p> : null}

        {editingPassage ? (
          <PassageEditor
            passage={editingPassage === "new" ? undefined : editingPassage}
            orderIndex={reading.passages.length}
            onCancel={() => setEditingPassage(null)}
            onSave={(body) => run(() => editingPassage === "new" ? createPassage(version.id, body) : updatePassage(editingPassage.id, body))}
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
                  <button onClick={() => setEditingPassage(passage)} className="btn btn-secondary">Edit passage</button>
                  <button onClick={() => run(() => deletePassage(passage.id))} className="btn btn-danger-ghost">Delete</button>
                </div>
              </div>

              <div className="question-group-list">
                {passage.question_groups.map((group) => (
                  <GroupSummary key={group.id} group={group} passageNumber={passage.order_index + 1} onMove={(offset) => moveGroup(passage.id, group.id, offset)} onEdit={() => setEditingGroup({ passageId: passage.id, group })} onDelete={() => run(() => deleteQuestionGroup(group.id))} />
                ))}
                {editingGroup?.passageId === passage.id ? (
                  <QuestionGroupEditor initial={editingGroup.group} nextQuestionNumber={nextNumber} passageBlocks={passage.blocks} passageNumber={passage.order_index + 1} onCancel={() => setEditingGroup(null)} onSave={(body) => run(() => editingGroup.group.id ? updateQuestionGroup(editingGroup.group.id, body) : createQuestionGroup(passage.id, body))} />
                ) : (
                  <NewGroupButton nextNumber={nextNumber} orderIndex={nextGroupOrder} passageBlocks={passage.blocks} onCreate={(group) => setEditingGroup({ passageId: passage.id, group })} />
                )}
              </div>
            </article>
          ))}
          {!reading.passages.length ? <div className="reading-inline-empty"><p>No passages yet.</p><span>Add a passage to begin authoring Reading content.</span></div> : null}
        </div>
      </section>
    </fieldset>
  );
}

function PassageEditor({ passage, orderIndex, onSave, onCancel }: { passage?: BuilderPassage; orderIndex: number; onSave: (body: { title: string; order_index: number; blocks: TextBlock[] }) => Promise<void>; onCancel: () => void }) {
  const [title, setTitle] = useState(passage?.title ?? "New reading passage");
  const [blocks, setBlocks] = useState<TextBlock[]>(passage?.blocks ?? [{ id: crypto.randomUUID(), type: "paragraph", label: "A", text: "Passage paragraph" }]);
  const [deletedReferences, setDeletedReferences] = useState<number[]>([]);
  const duplicateLabels = duplicateValues(blocks.filter((block) => block.type === "paragraph").map((block) => block.label ?? ""));
  const invalid = !title || !blocks.length || blocks.some((item) => !item.text || (item.type === "paragraph" && !item.label)) || duplicateLabels.length > 0;

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
    const references = passage?.question_groups.flatMap((group) => group.question_type === "matching_headings" ? group.questions.filter((question) => question.config.target_block_id === id).map((question) => question.number) : []) ?? [];
    setDeletedReferences((current) => [...new Set([...current, ...references])]);
    setBlocks(blocks.filter((block) => block.id !== id));
  }

  return (
    <div className="passage-editor">
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
        <div className="flex gap-2"><button type="button" onClick={onCancel} className="btn btn-ghost">Cancel</button><button type="button" disabled={invalid} onClick={() => onSave({ title, order_index: passage?.order_index ?? orderIndex, blocks })} className="btn btn-primary">Save passage</button></div>
      </div>
    </div>
  );
}

function GroupSummary({ group, passageNumber, onMove, onEdit, onDelete }: { group: BuilderQuestionGroup; passageNumber: number; onMove: (offset: number) => void; onEdit: () => void; onDelete: () => void }) {
  const numbers = group.questions.map((item) => item.number);
  const range = numbers.length > 1 ? `Q${Math.min(...numbers)}–${Math.max(...numbers)}` : `Q${numbers[0] ?? "—"}`;
  return (
    <div className="question-group-card">
      <span className="question-range">{range}</span>
      <div className="min-w-0 flex-1"><p>{questionRegistry[group.question_type].label}</p><span>{group.questions.length} question{group.questions.length === 1 ? "" : "s"} · {resolveQuestionGroupInstruction(group, { passageNumber }).intro}</span></div>
      <div className="group-actions"><button type="button" onClick={() => onMove(-1)} aria-label="Move question group up" className="icon-button">↑</button><button type="button" onClick={() => onMove(1)} aria-label="Move question group down" className="icon-button">↓</button><button onClick={onEdit} className="btn btn-secondary">Edit / Preview</button><button onClick={onDelete} className="btn btn-danger-ghost">Delete</button></div>
    </div>
  );
}

function NewGroupButton({ nextNumber, orderIndex, passageBlocks, onCreate }: { nextNumber: number; orderIndex: number; passageBlocks: TextBlock[]; onCreate: (group: QuestionGroupModel) => void }) {
  const [type, setType] = useState<QuestionType>("multiple_choice");
  function create() {
    const group = { ...questionRegistry[type].createDefault(nextNumber), order_index: orderIndex };
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
