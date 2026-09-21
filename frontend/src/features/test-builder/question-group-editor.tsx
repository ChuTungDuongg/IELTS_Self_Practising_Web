"use client";

import { useState } from "react";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, PassageBlock, QuestionGroupModel, TextCompletionLayout } from "@/features/questions/types";
import { isCompletionQuestionType, QuestionGroupInstruction, resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { textCompletionIntegrityErrors } from "@/features/questions/text-completion-integrity";
import { normalizeTextCompletionOrder } from "@/features/questions/text-completion-canvas";
import { useBuilderAutosave } from "./builder-lifecycle";

export function QuestionGroupEditor({
  initial,
  onSave,
  onAutosave,
  onCancel,
  nextQuestionNumber,
  baseQuestionNumber: requestedBaseQuestionNumber,
  passageBlocks,
  passageNumber,
}: {
  initial: QuestionGroupModel;
  onSave: (group: QuestionGroupModel) => Promise<void>;
  onAutosave?: (group: QuestionGroupModel) => Promise<unknown>;
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
  const structurallyValid = integrityErrors.length === 0 && questionGroupIsValid(presentedGroup, passageBlocks);
  const { saveNow } = useBuilderAutosave({
    resourceKey: `question-group:${initial.id ?? "new"}`,
    value: presentedGroup,
    save: (value) => (onAutosave ?? onSave)(value),
    valid: structurallyValid,
    enabled: Boolean(initial.id && onAutosave),
  });
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
          <button type="button" onClick={() => { if (initial.id && onAutosave) void saveNow().then((saved) => { if (saved) onCancel(); }); else onCancel(); }} className="btn btn-ghost">{initial.id ? "Close" : "Cancel"}</button>
          <button type="button" disabled={pending || !structurallyValid} onClick={async () => { setPending(true); try { if (initial.id && onAutosave) await saveNow(); else await onSave(presentedGroup); } finally { setPending(false); } }} className="btn btn-primary">{pending ? "Saving…" : initial.id ? "Save now" : "Create group"}</button>
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

function questionGroupIsValid(group: QuestionGroupModel, passageBlocks: PassageBlock[]): boolean {
  if (!group.questions.length || group.instruction.length > 4000) return false;
  const ids = group.questions.map((question) => question.id).filter(Boolean);
  const numbers = group.questions.map((question) => question.number);
  const orders = group.questions.map((question) => question.order_index);
  if (ids.length !== group.questions.length || new Set(ids).size !== ids.length || new Set(numbers).size !== numbers.length || new Set(orders).size !== orders.length) return false;
  if (group.questions.some((question) => question.number < 1 || question.order_index < 0 || !question.prompt.trim() || question.prompt.length > 5000 || !Object.keys(question.answer_key).length)) return false;

  const optionLists: Array<Array<{ id?: unknown; label?: unknown; text?: unknown }>> = [];
  for (const value of [group.config, ...group.questions.map((question) => question.config)]) {
    const options = value.options;
    if (Array.isArray(options)) optionLists.push(options as Array<{ id?: unknown; label?: unknown; text?: unknown }>);
  }
  if (optionLists.some((options) => {
    const optionIds = options.map((option) => String(option.id ?? "").trim());
    const labels = options.map((option) => String(option.label ?? "").trim().toLocaleLowerCase());
    return options.length < 2 || optionIds.some((id) => !id) || labels.some((label) => !label)
      || options.some((option) => !String(option.text ?? "").trim())
      || new Set(optionIds).size !== optionIds.length || new Set(labels).size !== labels.length;
  })) return false;

  const questionIds = new Set(ids.map(String));
  if (["plan_labelling", "map_labelling", "diagram_labelling"].includes(group.question_type)) {
    const markerIds = new Set(((group.config.markers as Array<{ question_id?: string }> | undefined) ?? []).map((marker) => String(marker.question_id ?? "")));
    if (markerIds.size !== questionIds.size || [...questionIds].some((id) => !markerIds.has(id))) return false;
  }
  if (["form_completion", "note_completion", "table_completion", "flow_chart_completion", "summary_completion", "sentence_completion"].includes(group.question_type)) {
    const layout = (group.config.layout ?? {}) as { rows?: Array<{ cells?: Array<{ type?: string; question_id?: string }> }>; nodes?: Array<{ type?: string; question_id?: string }> };
    const gaps = [...(layout.rows ?? []).flatMap((row) => row.cells ?? []), ...(layout.nodes ?? [])].filter((item) => item.type === "GAP").map((item) => String(item.question_id ?? ""));
    if (gaps.length !== questionIds.size || new Set(gaps).size !== gaps.length || gaps.some((id) => !questionIds.has(id))) return false;
  }
  if (group.question_type === "matching_headings") {
    const paragraphIds = new Set(passageBlocks.filter((block) => block.type === "paragraph").map((block) => block.id));
    if (group.questions.some((question) => !paragraphIds.has(String(question.config.target_block_id ?? "")))) return false;
  }
  return true;
}
