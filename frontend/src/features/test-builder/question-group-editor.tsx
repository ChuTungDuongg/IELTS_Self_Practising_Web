"use client";

import { useState } from "react";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, PassageBlock, QuestionGroupModel } from "@/features/questions/types";

export function QuestionGroupEditor({
  initial,
  onSave,
  onCancel,
  nextQuestionNumber,
  passageBlocks,
}: {
  initial: QuestionGroupModel;
  onSave: (group: QuestionGroupModel) => Promise<void>;
  onCancel: () => void;
  nextQuestionNumber: number;
  passageBlocks: PassageBlock[];
}) {
  const [group, setGroup] = useState(initial);
  const [preview, setPreview] = useState(false);
  const [pending, setPending] = useState(false);
  const definition = questionRegistry[group.question_type];
  const Editor = definition.BuilderEditor;
  const Renderer = definition.ExamRenderer;

  function addQuestion() {
    const nextNumber = Math.max(
      nextQuestionNumber,
      Math.max(0, ...group.questions.map((question) => question.number)) + 1,
    );
    const next = definition.createDefault(nextNumber).questions[0];
    if (group.question_type === "matching_headings") {
      next.config = {
        target_block_id: passageBlocks.find((block) => block.type === "paragraph")?.id ?? "",
      };
      next.answer_key = {
        kind: "SINGLE_OPTION",
        value: String((group.config.options as Array<{ id: string }>)[0]?.id ?? ""),
      };
    }
    setGroup({
      ...group,
      questions: [...group.questions, { ...next, order_index: group.questions.length }],
    });
  }

  return (
    <div className="group-editor">
      <div className="group-editor-header">
        <div className="min-w-0 flex-1">
          <p className="page-eyebrow">Question group · {definition.label}</p>
          <label className="field-label">Candidate instruction</label>
          <input
            value={group.instruction}
            onChange={(event) => setGroup({ ...group, instruction: event.target.value })}
            className="field mt-2"
            aria-label="Group instruction"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setPreview(!preview)} className="btn btn-secondary">{preview ? "Back to edit" : "Preview"}</button>
          <button type="button" onClick={onCancel} className="btn btn-ghost">Cancel</button>
          <button type="button" disabled={pending || !group.questions.length} onClick={async () => { setPending(true); try { await onSave(group); } finally { setPending(false); } }} className="btn btn-primary">{pending ? "Saving…" : "Save group"}</button>
        </div>
      </div>
      {preview ? (
        <div className="group-preview">
          <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Candidate preview</p>
          <p className="mb-4 text-sm font-medium">{group.instruction}</p>
          <Renderer group={group as ExamGroup} values={{}} passageBlocks={passageBlocks} disabled />
        </div>
      ) : (
        <>
          <Editor group={group} onChange={setGroup} passageBlocks={passageBlocks} />
          <button type="button" onClick={addQuestion} className="btn btn-secondary mt-4">+ Add question</button>
        </>
      )}
    </div>
  );
}
