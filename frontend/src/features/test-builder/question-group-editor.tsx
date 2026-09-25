"use client";

import { useRef, useState } from "react";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup, NoteCompletionLayout, PassageBlock, QuestionGroupModel, TableCompletionLayout, TextCompletionLayout } from "@/features/questions/types";
import { isCompletionQuestionType, QuestionGroupInstruction, resolveQuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { textCompletionIntegrityErrors } from "@/features/questions/text-completion-integrity";
import { normalizeTextCompletionOrder } from "@/features/questions/text-completion-canvas";
import { normalizeNoteCompletionOrder, noteCompletionIntegrityErrors } from "@/features/questions/note-completion";
import { diagramLabellingErrors, migrateLegacyDiagramGroup } from "@/features/questions/diagram-labelling";
import { useBuilderAutosave } from "./builder-lifecycle";
import { QuestionImageAttachment } from "./question-image-attachment";
import type { BuilderQuestionGroup } from "@/lib/api/builder";

export function QuestionGroupEditor({
  initial,
  onSave,
  onAutosave,
  onPersisted,
  onCancel,
  nextQuestionNumber,
  baseQuestionNumber: requestedBaseQuestionNumber,
  passageBlocks,
  passageNumber,
  testVersionId,
  moduleType,
}: {
  initial: QuestionGroupModel;
  onSave: (group: QuestionGroupModel) => Promise<void>;
  onAutosave?: (group: QuestionGroupModel, expectedRevision: number) => Promise<BuilderQuestionGroup>;
  onPersisted?: (group: BuilderQuestionGroup) => void;
  onCancel: () => void;
  nextQuestionNumber: number;
  baseQuestionNumber?: number;
  passageBlocks: PassageBlock[];
  passageNumber?: number;
  testVersionId?: string;
  moduleType?: "READING" | "LISTENING";
}) {
  const [group, setGroup] = useState(() => {
    const migrated = migrateLegacyDiagramGroup(initial);
    if (
      moduleType === "LISTENING"
      && ["plan_labelling", "map_labelling"].includes(migrated.question_type)
    ) {
      return { ...migrated, config: { options: migrated.config.options } };
    }
    return migrated;
  });
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
    : group.question_type === "note_completion"
      ? normalizeNoteCompletionOrder(group, {
          ...(group.config.layout as NoteCompletionLayout),
          title: (group.config.layout as NoteCompletionLayout).title?.trim() ?? "",
        }, baseQuestionNumber)
    : group.question_type === "table_completion"
      ? {
          ...group,
          config: {
            ...group.config,
            layout: {
              ...(group.config.layout as TableCompletionLayout),
              title: (group.config.layout as TableCompletionLayout).title?.trim() ?? "",
            },
          },
        }
      : group;
  const integrityErrors = group.question_type === "text_completion"
    ? textCompletionIntegrityErrors(group)
    : group.question_type === "note_completion"
      ? noteCompletionIntegrityErrors(group)
      : [];
  const diagramErrors = diagramLabellingErrors(presentedGroup);
  const structurallyValid = integrityErrors.length === 0 && diagramErrors.length === 0 && questionGroupIsValid(presentedGroup, passageBlocks, moduleType);
  const saveIssue = structurallyValid ? null : integrityErrors[0] ?? diagramErrors[0] ?? questionGroupSaveIssue(presentedGroup);
  const revision = useRef(initial.revision ?? 1);
  const { markSaved, saveNow } = useBuilderAutosave({
    resourceKey: `question-group:${initial.id ?? "new"}`,
    value: presentedGroup,
    save: async (value) => {
      if (!onAutosave) { await onSave(value); return; }
      const saved = await onAutosave(value, revision.current);
      revision.current = saved.revision;
      return saved;
    },
    onSaved: (saved, _submitted, unchanged) => {
      if (!saved) return;
      onPersisted?.(saved);
      if (unchanged) {
        setGroup(saved);
        return saved;
      }
    },
    valid: structurallyValid,
    enabled: Boolean(initial.id && onAutosave),
  });
  const usesMultilineInstruction = isCompletionQuestionType(group.question_type);

  function addQuestion() {
    const nextNumber = Math.max(
      nextQuestionNumber,
      Math.max(0, ...group.questions.map((question) => question.number)) + 1,
    );
    const template = definition.createDefault(nextNumber, { moduleType });
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
    if (["plan_labelling", "map_labelling"].includes(group.question_type)) {
      if (Array.isArray(group.config.markers) && Array.isArray(template.config.markers)) {
        const marker = (template.config.markers as Array<Record<string, unknown>>)[0];
        config = { ...group.config, markers: [...group.config.markers, marker] };
      }
      next.answer_key = { kind: "SINGLE_OPTION", value: String((group.config.options as Array<{ id: string }>)[0]?.id ?? "") };
    }
    if (["form_completion", "flow_chart_completion", "summary_completion", "sentence_completion"].includes(group.question_type)) {
      const layout = group.config.layout as { kind: string; columns?: unknown[]; rows?: unknown[]; nodes?: unknown[] };
      const templateLayout = template.config.layout as typeof layout;
      config = { ...group.config, layout: { ...layout, nodes: [...(layout.nodes ?? []), ...(templateLayout.nodes ?? []).filter((_, index) => index > 0)] } };
    }
    setGroup({
      ...group,
      config,
      questions: [...group.questions, { ...next, order_index: group.questions.length }],
    });
  }

  return (
    <fieldset className="group-editor" disabled={pending} aria-busy={pending}>
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
          <button type="button" onClick={() => { if (preview || !initial.id || !onAutosave) setPreview(!preview); else void saveNow().then((saved) => { if (saved) setPreview(true); }); }} className="btn btn-secondary">{preview ? "Back to edit" : "Preview"}</button>
          <button type="button" onClick={() => { if (initial.id && onAutosave) void saveNow().then((saved) => { if (saved) onCancel(); }); else onCancel(); }} className="btn btn-ghost">{initial.id ? "Close" : "Cancel"}</button>
          <button type="button" disabled={pending || !structurallyValid} onClick={async () => { setPending(true); try { if (initial.id && onAutosave) await saveNow(); else { await onSave(presentedGroup); markSaved(); } } finally { setPending(false); } }} className="btn btn-primary">{pending ? "Saving…" : initial.id ? "Save now" : "Save group"}</button>
        </div>
      </div>
      {integrityErrors.length ? <div role="alert" className="notice notice-warning">{integrityErrors.map((message) => <p key={message}>{message}</p>)}</div> : null}
      {diagramErrors.length && preview ? <div role="alert" className="notice notice-warning">{diagramErrors.map((message) => <p key={message}>{message}</p>)}</div> : null}
      {saveIssue && !integrityErrors.length && !diagramErrors.length ? <p role="alert" className="notice notice-warning">{saveIssue}</p> : null}
      {preview ? (
        <div className="group-preview">
          <p className="mb-2 text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Candidate preview</p>
          <QuestionGroupInstruction group={presentedGroup} passageNumber={passageNumber} />
          <Renderer group={presentedGroup as ExamGroup} values={{}} passageBlocks={passageBlocks} disabled />
        </div>
      ) : (
        <>
          {testVersionId && ["plan_labelling", "map_labelling", "diagram_labelling"].includes(group.question_type) ? <QuestionImageAttachment group={group} testVersionId={testVersionId} onChange={setGroup} /> : null}
          <Editor group={group} onChange={setGroup} passageBlocks={passageBlocks} baseQuestionNumber={baseQuestionNumber} moduleType={moduleType} />
          {!["text_completion", "diagram_labelling", "table_completion", "note_completion", "multiple_choice_multiple"].includes(group.question_type) ? <button type="button" onClick={addQuestion} className="btn btn-secondary mt-4">+ Add question</button> : null}
        </>
      )}
    </fieldset>
  );
}

function questionGroupIsValid(group: QuestionGroupModel, passageBlocks: PassageBlock[], moduleType?: "READING" | "LISTENING"): boolean {
  if (!group.questions.length || group.instruction.length > 4000) return false;
  const ids = group.questions.map((question) => question.id).filter(Boolean);
  const numbers = group.questions.map((question) => question.number);
  const orders = group.questions.map((question) => question.order_index);
  if (ids.length !== group.questions.length || new Set(ids).size !== ids.length || new Set(numbers).size !== numbers.length || new Set(orders).size !== orders.length) return false;
  if (group.questions.some((question) => question.number < 1 || question.order_index < 0 || !question.prompt.trim() || question.prompt.length > 5000)) return false;
  if (group.question_type === "multiple_choice_multiple" && group.questions.some((question) => {
    const minimum = Number(question.config.min_selections);
    const maximum = Number(question.config.max_selections);
    return !Number.isInteger(minimum) || minimum < 1 || minimum !== maximum || question.number + maximum - 1 > 40;
  })) return false;

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
  if (["plan_labelling", "map_labelling"].includes(group.question_type) && moduleType !== "LISTENING") {
    const markerIds = new Set(((group.config.markers as Array<{ question_id?: string }> | undefined) ?? []).map((marker) => String(marker.question_id ?? "")));
    if (markerIds.size !== questionIds.size || [...questionIds].some((id) => !markerIds.has(id))) return false;
  }
  if (group.question_type === "diagram_labelling" && diagramLabellingErrors(group).length) return false;
  if (group.question_type === "table_completion") {
    const layout = (group.config.layout ?? {}) as {
      title?: string;
      columns?: unknown[];
      rows?: Array<{ cells?: Array<{ segments?: Array<{ type?: string; text?: string; question_id?: string }> }> }>;
    };
    if ((layout.title?.trim().length ?? 0) > 300 || !layout.columns?.length || !layout.rows?.length) return false;
    if (layout.rows.some((row) => row.cells?.length !== layout.columns?.length)) return false;
    if (layout.rows.some((row) => row.cells?.some((cell) => !cell.segments?.length || cell.segments.some((segment) => (
      (segment.type !== "TEXT" && segment.type !== "GAP")
      || (segment.type === "TEXT" && (typeof segment.text !== "string" || Boolean(segment.question_id)))
      || (segment.type === "GAP" && !segment.question_id)
    ))))) return false;
    const gaps = layout.rows
      .flatMap((row) => row.cells ?? [])
      .flatMap((cell) => cell.segments ?? [])
      .filter((segment) => segment.type === "GAP")
      .map((segment) => String(segment.question_id ?? ""));
    if (gaps.length !== questionIds.size || new Set(gaps).size !== gaps.length || gaps.some((id) => !questionIds.has(id))) return false;
  }
  if (group.question_type === "note_completion") {
    const layout = group.config.layout as NoteCompletionLayout;
    const gaps = layout.blocks.flatMap((block) => block.segments)
      .filter((segment) => segment.type === "GAP")
      .map((segment) => segment.question_id);
    if (gaps.length !== questionIds.size || new Set(gaps).size !== gaps.length || gaps.some((id) => !questionIds.has(id))) return false;
  }
  if (["form_completion", "flow_chart_completion", "summary_completion", "sentence_completion"].includes(group.question_type)) {
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

function questionGroupSaveIssue(group: QuestionGroupModel): string {
  if (!group.questions.length) return "Add at least one question before saving this group.";
  if (group.instruction.length > 4000) return "Group instructions must be 4,000 characters or fewer.";
  const ids = group.questions.map((question) => question.id);
  if (ids.some((id) => !id) || new Set(ids).size !== ids.length) return "Question IDs must be present and unique.";
  const numbers = group.questions.map((question) => question.number);
  if (new Set(numbers).size !== numbers.length) return "Question numbers are duplicated.";
  if (group.questions.some((question) => !question.prompt.trim())) return "Each question needs prompt text before it can be saved.";
  for (const config of [group.config, ...group.questions.map((question) => question.config)]) {
    const options = config.options as Array<{ id?: string; label?: string; text?: string }> | undefined;
    if (!Array.isArray(options)) continue;
    const labels = options.map((option) => String(option.label ?? "").trim().toLocaleLowerCase());
    if (new Set(labels).size !== labels.length) return "Option labels must be unique.";
    if (options.some((option) => !option.id || !String(option.label ?? "").trim() || !String(option.text ?? "").trim())) return "Every option needs a label, text, and stable ID.";
  }
  if (group.question_type === "multiple_choice_multiple") return "Required selections and the numbered question range must be valid.";
  return "This group has an invalid layout or question reference. Check its gaps, markers, and linked questions.";
}
