"use client";

import { useState } from "react";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, QuestionGroupModel } from "@/features/questions/types";

export function QuestionGroupEditor({
  initial,
  onSave,
  onCancel,
  nextQuestionNumber,
}: {
  initial: QuestionGroupModel;
  onSave: (group: QuestionGroupModel) => Promise<void>;
  onCancel: () => void;
  nextQuestionNumber: number;
}) {
  const [group, setGroup] = useState(initial);
  const [preview, setPreview] = useState(false);
  const [pending, setPending] = useState(false);
  const definition = questionRegistry[group.question_type];
  const Editor = definition.BuilderEditor;
  const Renderer = definition.ExamRenderer;

  function addQuestion() {
    const next = definition.createDefault(nextQuestionNumber).questions[0];
    setGroup({
      ...group,
      questions: [...group.questions, { ...next, order_index: group.questions.length }],
    });
  }

  return (
    <div className="rounded-xl border-2 border-[var(--accent)] bg-[var(--surface)] p-5">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--accent)]">{definition.label}</p>
          <input
            value={group.instruction}
            onChange={(event) => setGroup({ ...group, instruction: event.target.value })}
            className="mt-2 w-full min-w-80 rounded-md border border-[var(--line)] px-3 py-2"
            aria-label="Group instruction"
          />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => setPreview(!preview)} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-semibold">{preview ? "Edit" : "Preview"}</button>
          <button type="button" onClick={onCancel} className="rounded-md border border-[var(--line)] px-3 py-2 text-sm">Cancel</button>
          <button type="button" disabled={pending || !group.questions.length} onClick={async () => { setPending(true); try { await onSave(group); } finally { setPending(false); } }} className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{pending ? "Saving…" : "Save group"}</button>
        </div>
      </div>
      {preview ? (
        <div className="rounded-lg bg-[var(--surface-soft)] p-5">
          <p className="mb-4 text-sm font-medium">{group.instruction}</p>
          <Renderer group={group as ExamGroup} values={{}} disabled />
        </div>
      ) : (
        <>
          <Editor group={group} onChange={setGroup} />
          <button type="button" onClick={addQuestion} className="mt-4 text-sm font-semibold text-[var(--accent)]">+ Add question</button>
        </>
      )}
    </div>
  );
}
