"use client";

import { useState } from "react";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, PassageBlock, QuestionGroupModel, TextCompletionLayout } from "@/features/questions/types";
import { isCompletionQuestionType, QuestionGroupInstruction, resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { textCompletionIntegrityErrors } from "@/features/questions/text-completion-integrity";
import { normalizeTextCompletionOrder } from "@/features/questions/text-completion-canvas";

export function QuestionGroupEditor({
  initial,
  onSave,
  onCancel,
  nextQuestionNumber,
  baseQuestionNumber: requestedBaseQuestionNumber,
  passageBlocks,
  passageNumber,
}: {
  initial: QuestionGroupModel;
  onSave: (group: QuestionGroupModel) => Promise<void>;
  onCancel: () => void;
  nextQuestionNumber: number;
  baseQuestionNumber?: number;
  passageBlocks: PassageBlock[];
  passageNumber?: number;
}) {
  const [group, setGroup] = useState(initial);
  const [preview, setPreview] = useState(false);
  const [pending, setPending] = useState(false);
  const definition = questionRegistry[group.question_type];
  const Editor = definition.BuilderEditor;
  const Renderer = definition.ExamRenderer;
  const baseQuestionNumber = requestedBaseQuestionNumber ?? (group.questions.length
    ? Math.min(...group.questions.map((question) => question.number))
    : nextQuestionNumber);
  const presentedGroup = group.question_type === "text_completion"
    ? normalizeTextCompletionOrder(group, group.config as unknown as TextCompletionLayout, baseQuestionNumber)
    : group;
  const integrityErrors = group.question_type === "text_completion" ? textCompletionIntegrityErrors(group) : [];
  const usesMultilineInstruction = isCompletionQuestionType(group.question_type);

  function addQuestion() {
    const nextNumber = Math.max(
      nextQuestionNumber,
      Math.max(0, ...group.questions.map((question) => question.number)) + 1,
    );
    const template = definition.createDefault(nextNumber);
    const next = template.questions[0];
    let config = group.config;
    if (group.question_type === "matching_headings") {
      next.config = {
        target_block_id: passageBlocks.find((block) => block.type === "paragraph")?.id ?? "",
      };
      next.answer_key = {
        kind: "SINGLE_OPTION",
        value: String((group.config.options as Array<{ id: string }>)[0]?.id ?? ""),
      };
    }
    if (group.question_type === "matching") {
      next.answer_key = {
        kind: "SINGLE_OPTION",
        value: String((group.config.options as Array<{ id: string }>)[0]?.id ?? ""),
      };
    }
    if (["plan_labelling", "map_labelling", "diagram_labelling"].includes(group.question_type)) {
      const marker = (template.config.markers as Array<Record<string, unknown>>)[0];
      config = { ...group.config, markers: [...(group.config.markers as Array<Record<string, unknown>>), marker] };
      next.answer_key = { kind: "SINGLE_OPTION", value: String((group.config.options as Array<{ id: string }>)[0]?.id ?? "") };
    }
    if (["form_completion", "note_completion", "table_completion", "flow_chart_completion", "summary_completion", "sentence_completion"].includes(group.question_type)) {
      const layout = group.config.layout as { kind: string; columns?: unknown[]; rows?: unknown[]; nodes?: unknown[] };
      const templateLayout = template.config.layout as typeof layout;
      config = layout.kind === "TABLE"
        ? { ...group.config, layout: { ...layout, rows: [...(layout.rows ?? []), ...(templateLayout.rows ?? [])] } }
        : { ...group.config, layout: { ...layout, nodes: [...(layout.nodes ?? []), ...(templateLayout.nodes ?? []).filter((_, index) => index > 0)] } };
    }
    setGroup({
      ...group,
      config,
      questions: [...group.questions, { ...next, order_index: group.questions.length }],
    });
  }

  return (
    <div className="group-editor">
      <div className="group-editor-header">
        <div className="min-w-0 flex-1">
          <p className="page-eyebrow">Question group · {definition.label}</p>
          {usesMultilineInstruction ? (
            <label className="field-label">
              Candidate instructions
              <textarea
                value={group.instruction}
                onChange={(event) => setGroup({ ...group, instruction: event.target.value })}
                className="field mt-2 min-h-24 resize-y"
                aria-label="Candidate instructions"
                placeholder={resolveQuestionGroupInstruction({ ...group, instruction: "" }, { passageNumber }).intro}
              />
              <span className="mt-1 block font-normal text-[var(--muted)]">Line breaks are preserved in Candidate, Preview and Review.</span>
            </label>
          ) : (
            <>
              <label className="field-label">Custom candidate instruction <span className="font-normal text-[var(--muted)]">(optional)</span></label>
              <input
                value={group.instruction}
                onChange={(event) => setGroup({ ...group, instruction: event.target.value })}
                className="field mt-2"
                aria-label="Group instruction"
                placeholder={resolveQuestionGroupInstruction({ ...group, instruction: "" }, { passageNumber }).intro}
              />
            </>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setPreview(!preview)} className="btn btn-secondary">{preview ? "Back to edit" : "Preview"}</button>
          <button type="button" onClick={onCancel} className="btn btn-ghost">Cancel</button>
          <button type="button" disabled={pending || !presentedGroup.questions.length || integrityErrors.length > 0} onClick={async () => { if (integrityErrors.length) return; setPending(true); try { await onSave(presentedGroup); } finally { setPending(false); } }} className="btn btn-primary">{pending ? "Saving…" : "Save group"}</button>
        </div>
      </div>
      {integrityErrors.length ? <div role="alert" className="notice notice-warning">{integrityErrors.map((message) => <p key={message}>{message}</p>)}</div> : null}
      {preview ? (
        <div className="group-preview">
          <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Candidate preview</p>
          <QuestionGroupInstruction group={presentedGroup} passageNumber={passageNumber} />
          <Renderer group={presentedGroup as ExamGroup} values={{}} passageBlocks={passageBlocks} disabled />
        </div>
      ) : (
        <>
          <Editor group={group} onChange={setGroup} passageBlocks={passageBlocks} baseQuestionNumber={baseQuestionNumber} />
          {group.question_type !== "text_completion" ? <button type="button" onClick={addQuestion} className="btn btn-secondary mt-4">+ Add question</button> : null}
        </>
      )}
    </div>
  );
}
