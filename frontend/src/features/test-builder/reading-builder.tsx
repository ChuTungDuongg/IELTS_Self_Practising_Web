"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  createPassage,
  createQuestionGroup,
  createReadingModule,
  deletePassage,
  deleteQuestionGroup,
  updatePassage,
  updateQuestionGroup,
  type BuilderPassage,
  type BuilderQuestionGroup,
  type BuilderVersion,
  type TextBlock,
} from "@/lib/api/builder";
import { questionRegistry, questionTypeOptions } from "@/features/questions/registry";
import type { QuestionGroupModel, QuestionType } from "@/features/questions/types";
import { QuestionGroupEditor } from "./question-group-editor";

export function ReadingBuilder({ version }: { version: BuilderVersion }) {
  const router = useRouter();
  const reading = version.modules.find((item) => item.module_type === "READING");
  const [editingPassage, setEditingPassage] = useState<BuilderPassage | "new" | null>(null);
  const [editingGroup, setEditingGroup] = useState<{ passageId: string; group: QuestionGroupModel } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const nextNumber = useMemo(() => Math.max(0, ...(reading?.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => question.number))) ?? [])) + 1, [reading]);

  async function run(action: () => Promise<unknown>) {
    setMessage(null);
    try {
      await action();
      setEditingPassage(null);
      setEditingGroup(null);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The builder change could not be saved.");
    }
  }

  if (!reading) {
    return <section className="mt-8 rounded-xl border border-dashed border-[var(--line)] p-8 text-center"><h2 className="font-semibold">Reading module</h2><p className="mt-2 text-sm text-[var(--muted)]">Create the module before adding passages and question groups.</p><button onClick={() => run(() => createReadingModule(version.id))} className="mt-4 rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white">Create Reading module</button>{message ? <p className="mt-3 text-sm text-red-700">{message}</p> : null}</section>;
  }

  return (
    <section className="mt-8">
      <div className="mb-4 flex items-center justify-between"><div><h2 className="text-xl font-semibold">Reading Builder</h2><p className="mt-1 text-sm text-[var(--muted)]">Stable passage blocks · structured questions · inline answer keys</p></div><button onClick={() => setEditingPassage("new")} className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-semibold text-white">Add passage</button></div>
      {message ? <p role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-800">{message}</p> : null}
      {editingPassage ? <PassageEditor passage={editingPassage === "new" ? undefined : editingPassage} orderIndex={reading.passages.length} onCancel={() => setEditingPassage(null)} onSave={(body) => run(() => editingPassage === "new" ? createPassage(version.id, body) : updatePassage(editingPassage.id, body))} /> : null}
      <div className="space-y-5">
        {reading.passages.map((passage) => (
          <article key={passage.id} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">Passage {passage.order_index + 1}</p><h3 className="mt-1 text-lg font-semibold">{passage.title}</h3><p className="mt-1 text-sm text-[var(--muted)]">{passage.blocks.length} blocks · {passage.question_groups.length} groups</p></div><div className="flex gap-2"><button onClick={() => setEditingPassage(passage)} className="text-sm font-semibold">Edit passage</button><button onClick={() => run(() => deletePassage(passage.id))} className="text-sm text-red-700">Delete</button></div></div>
            <div className="mt-5 space-y-3">
              {passage.question_groups.map((group) => <GroupSummary key={group.id} group={group} onEdit={() => setEditingGroup({ passageId: passage.id, group })} onDelete={() => run(() => deleteQuestionGroup(group.id))} />)}
              {editingGroup?.passageId === passage.id ? <QuestionGroupEditor initial={editingGroup.group} nextQuestionNumber={nextNumber} onCancel={() => setEditingGroup(null)} onSave={(body) => run(() => editingGroup.group.id ? updateQuestionGroup(editingGroup.group.id, body) : createQuestionGroup(passage.id, body))} /> : <NewGroupButton nextNumber={nextNumber} orderIndex={passage.question_groups.length} onCreate={(group) => setEditingGroup({ passageId: passage.id, group })} />}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function PassageEditor({ passage, orderIndex, onSave, onCancel }: { passage?: BuilderPassage; orderIndex: number; onSave: (body: { title: string; order_index: number; blocks: TextBlock[] }) => Promise<void>; onCancel: () => void }) {
  const [title, setTitle] = useState(passage?.title ?? "New reading passage");
  const [blocks, setBlocks] = useState<TextBlock[]>(passage?.blocks ?? [{ id: crypto.randomUUID(), type: "paragraph", text: "Passage paragraph" }]);
  return <div className="mb-5 rounded-xl border-2 border-[var(--accent)] bg-[var(--surface)] p-5"><label className="block text-sm font-medium">Passage title<input value={title} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label><div className="mt-4 space-y-3">{blocks.map((block, index) => <div key={block.id} className="flex gap-2"><select value={block.type} onChange={(event) => setBlocks(blocks.map((item, itemIndex) => itemIndex === index ? { ...item, type: event.target.value as TextBlock["type"] } : item))} className="rounded-md border border-[var(--line)] px-2"><option value="paragraph">Paragraph</option><option value="heading">Heading</option></select><textarea value={block.text} onChange={(event) => setBlocks(blocks.map((item, itemIndex) => itemIndex === index ? { ...item, text: event.target.value } : item))} rows={3} className="flex-1 rounded-md border border-[var(--line)] px-3 py-2" /><button type="button" onClick={() => setBlocks(blocks.filter((_, itemIndex) => itemIndex !== index))} className="text-sm text-red-700">Remove</button></div>)}</div><div className="mt-4 flex gap-2"><button type="button" onClick={() => setBlocks([...blocks, { id: crypto.randomUUID(), type: "paragraph", text: "New paragraph" }])} className="text-sm font-semibold text-[var(--accent)]">+ Add block</button><div className="flex-1" /><button onClick={onCancel} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm">Cancel</button><button disabled={!title || !blocks.length || blocks.some((item) => !item.text)} onClick={() => onSave({ title, order_index: passage?.order_index ?? orderIndex, blocks })} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Save passage</button></div></div>;
}

function GroupSummary({ group, onEdit, onDelete }: { group: BuilderQuestionGroup; onEdit: () => void; onDelete: () => void }) {
  return <div className="flex items-center gap-4 rounded-lg bg-[var(--surface-soft)] p-4"><div className="flex-1"><p className="font-medium">{questionRegistry[group.question_type].label}</p><p className="mt-1 text-sm text-[var(--muted)]">Questions {group.questions.map((item) => item.number).join(", ")}</p></div><button onClick={onEdit} className="text-sm font-semibold">Edit / Preview</button><button onClick={onDelete} className="text-sm text-red-700">Delete</button></div>;
}

function NewGroupButton({ nextNumber, orderIndex, onCreate }: { nextNumber: number; orderIndex: number; onCreate: (group: QuestionGroupModel) => void }) {
  const [type, setType] = useState<QuestionType>("multiple_choice");
  return <div className="flex flex-wrap gap-2"><select value={type} onChange={(event) => setType(event.target.value as QuestionType)} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm">{questionTypeOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><button onClick={() => onCreate({ ...questionRegistry[type].createDefault(nextNumber), order_index: orderIndex })} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-semibold">+ Add question group</button></div>;
}
