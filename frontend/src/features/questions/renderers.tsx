"use client";

import type { ExamGroup, ExamQuestion, Option, PassageBlock, TextCompletionLayout } from "./types";
import { assetContentUrl } from "@/lib/api/assets";
import { SelectableText, type HighlightController } from "@/features/highlighting/selectable-text";
import { questionSpan } from "./numbering";

/* eslint-disable @next/next/no-img-element -- exam assets have dynamic dimensions and must retain intrinsic ratio */

export type RendererProps = {
  group: ExamGroup;
  values: Record<string, unknown>;
  disabled?: boolean;
  onAnswer?: (questionId: string, value: string | string[]) => void;
  passageBlocks?: PassageBlock[];
  highlighting?: HighlightController;
  activeQuestionId?: string | null;
  presentation?: "default" | "listening-visual";
};

export function questionTarget(question: ExamQuestion, activeQuestionId?: string | null, className = "") {
  return {
    id: `question-${question.id}`,
    "data-question-id": question.id,
    tabIndex: -1,
    className: `${className} exam-question-target ${activeQuestionId === question.id ? "is-navigation-target" : ""}`.trim(),
  };
}

function QuestionHeader({ question, highlighting, numberLabel }: { question: ExamQuestion; highlighting?: HighlightController; numberLabel?: string }) {
  return <p className="font-medium"><span className="mr-2 text-[var(--accent)]">{numberLabel ?? question.number}</span><SelectableText text={question.prompt} target={{ target_kind: "QUESTION_PROMPT", target_id: question.id }} controller={highlighting} /></p>;
}

export function MultipleChoiceRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  return <div className="space-y-5">{group.questions.map((question) => <fieldset key={question.id} {...questionTarget(question, activeQuestionId)}><QuestionHeader question={question} highlighting={highlighting} /><div className="mt-2 space-y-2">{(question.config.options as Option[]).map((option) => <label key={option.id} className="flex items-start gap-2"><input type="radio" disabled={disabled} name={question.id} checked={values[question.id] === option.id} onChange={() => onAnswer?.(question.id, option.id)} /><span><b>{option.label}.</b> {option.text}</span></label>)}</div></fieldset>)}</div>;
}

export function MultipleChoiceMultipleRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  return <div className="space-y-5">{group.questions.map((question) => { const selected = new Set(Array.isArray(values[question.id]) ? values[question.id] as string[] : []); const required = questionSpan(group.question_type, question.config); const end = question.number + required - 1; return <fieldset key={question.id} {...questionTarget(question, activeQuestionId)}><QuestionHeader question={question} highlighting={highlighting} numberLabel={end === question.number ? String(question.number) : `${question.number}–${end}`} /><div className="mt-2 space-y-2">{(question.config.options as Option[]).map((option) => <label key={option.id} className="flex items-start gap-2"><input type="checkbox" disabled={disabled || (!selected.has(option.id) && selected.size >= required)} checked={selected.has(option.id)} onChange={() => onAnswer?.(question.id, selected.has(option.id) ? [...selected].filter((id) => id !== option.id) : [...selected, option.id])} /><span><b>{option.label}.</b> {option.text}</span></label>)}</div></fieldset>; })}</div>;
}

export function MatchingRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  const options = group.config.options as Option[];
  return <div className="space-y-4">{group.questions.map((question) => <div key={question.id} {...questionTarget(question, activeQuestionId, "grid gap-2 sm:grid-cols-[1fr_16rem]")}><QuestionHeader question={question} highlighting={highlighting} /><select aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="select-field"><option value="">Choose an answer</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></div>)}</div>;
}

export function VisualLabellingRenderer(props: RendererProps) {
  const { group } = props;
  const markers = Array.isArray(group.config.markers)
    ? group.config.markers as Array<{ id: string; question_id: string; x: number; y: number }>
    : null;
  const image = group.image_asset ?? (group.config.image_asset as typeof group.image_asset);
  const noun = group.question_type === "map_labelling" ? "map" : "plan";
  if (props.presentation === "listening-visual") {
    return <div className="listening-visual-layout">
      <div className="listening-visual-pane">{image ? <div className="visual-question"><img src={assetContentUrl(image)} alt={`Listening ${noun}`} /></div> : <p className="notice">The {noun} image is unavailable.</p>}</div>
      <div className="listening-visual-answer-pane"><MatchingRenderer {...props} presentation="default" /></div>
    </div>;
  }
  return <div className="space-y-5">{image ? <div className="visual-question"><img src={assetContentUrl(image)} alt={`${markers ? "Reading" : "Listening"} ${noun}`} />{markers?.map((marker) => <span key={marker.id} className="visual-marker" style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}>{group.questions.find((item) => item.id === marker.question_id)?.number ?? "?"}</span>)}</div> : null}<MatchingRenderer {...props} /></div>;
}

export function StructuredCompletionRenderer(props: RendererProps) {
  const { group, values, disabled, onAnswer, activeQuestionId } = props;
  const layout = group.config.layout as { kind: string; columns?: Array<{ id: string; label: string }>; rows?: Array<{ id: string; cells: Array<{ id: string; type: "TEXT" | "GAP"; text: string; question_id?: string }> }>; nodes?: Array<{ id: string; type: "TEXT" | "GAP"; text: string; question_id?: string; level: number }> };
  const gap = (questionId?: string) => { const question = group.questions.find((item) => item.id === questionId); return question ? <label {...questionTarget(question, activeQuestionId, "structured-answer")}><span>{question.number}</span><input aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} /></label> : null; };
  if (layout.kind === "TABLE") return <div className="overflow-x-auto"><table className="completion-table"><thead><tr>{layout.columns?.map((column) => <th key={column.id}>{column.label}</th>)}</tr></thead><tbody>{layout.rows?.map((row) => <tr key={row.id}>{row.cells.map((cell) => <td key={cell.id}>{cell.type === "GAP" ? gap(cell.question_id) : cell.text}</td>)}</tr>)}</tbody></table></div>;
  return <div className={`completion-layout completion-${layout.kind.toLowerCase()}`}>{layout.nodes?.map((node) => <div key={node.id} className="completion-node" style={{ marginLeft: `${node.level * 20}px` }}>{node.type === "GAP" ? gap(node.question_id) : node.text}</div>)}</div>;
}

export function TrueFalseNotGivenRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  return <AgreementRenderer group={group} values={values} disabled={disabled} onAnswer={onAnswer} highlighting={highlighting} activeQuestionId={activeQuestionId} choices={["TRUE", "FALSE", "NOT_GIVEN"]} />;
}

export function YesNoNotGivenRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  return <AgreementRenderer group={group} values={values} disabled={disabled} onAnswer={onAnswer} highlighting={highlighting} activeQuestionId={activeQuestionId} choices={["YES", "NO", "NOT_GIVEN"]} />;
}

function AgreementRenderer({ group, values, disabled, onAnswer, highlighting, choices, activeQuestionId }: RendererProps & { choices: string[] }) {
  return <div className="space-y-5">{group.questions.map((question) => <fieldset key={question.id} {...questionTarget(question, activeQuestionId)}><QuestionHeader question={question} highlighting={highlighting} /><div className="mt-2 flex flex-wrap gap-4">{choices.map((choice) => <label key={choice} className="flex items-center gap-2"><input type="radio" disabled={disabled} name={question.id} checked={values[question.id] === choice} onChange={() => onAnswer?.(question.id, choice)} />{choice.replace("_", " ")}</label>)}</div></fieldset>)}</div>;
}

export function TextCompletionRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  const layout = group.config as unknown as TextCompletionLayout;
  if (!layout.blocks) return <div className="space-y-4">{group.questions.map((question) => <div key={question.id} {...questionTarget(question, activeQuestionId, "block")}><QuestionHeader question={question} highlighting={highlighting} /><input aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="mt-2 w-full rounded-md border border-[var(--line)] px-3 py-2" /></div>)}</div>;
  return (
    <div className={`text-completion-layout text-completion-${layout.mode.toLowerCase()}`}>
      {layout.mode === "PASSAGE" && layout.title?.trim() ? <h3 className="completion-content-title">{layout.title.trim()}</h3> : null}
      {layout.blocks.map((block) => (
        <div key={block.id} className="text-completion-block text-completion-line">
          {block.segments.map((segment) => {
            if (segment.type === "TEXT") return <SelectableText key={segment.id} text={segment.text ?? ""} target={{ target_kind: "TEXT_COMPLETION_SEGMENT", target_id: group.id, segment_id: segment.id }} controller={highlighting} />;
            const question = group.questions.find((item) => item.id === segment.question_id);
            return question ? (
              <label key={segment.id} {...questionTarget(question, activeQuestionId, "completion-gap-inline")}>
                <span className="completion-gap-number">{question.number}</span>
                <input
                  aria-label={`Question ${question.number}`}
                  disabled={disabled}
                  value={String(values[question.id] ?? "")}
                  onChange={(event) => onAnswer?.(question.id, event.target.value)}
                  className="completion-gap-input"
                />
              </label>
            ) : null;
          })}
        </div>
      ))}
    </div>
  );
}

export function MatchingHeadingsRenderer({ group, values, disabled, onAnswer, passageBlocks = [], highlighting, activeQuestionId }: RendererProps) {
  const options = group.config.options as Option[];
  const paragraphs = new Map(passageBlocks.map((block) => [block.id, block]));
  return <div><ol className="matching-heading-options">{options.map((option) => <li key={option.id} className="matching-heading-option"><b className="matching-heading-label">{option.label}.</b><SelectableText className="matching-heading-text" text={option.text} target={{ target_kind: "QUESTION_GROUP_OPTION", target_id: group.id, segment_id: option.id }} controller={highlighting} /></li>)}</ol><div className="space-y-4">{group.questions.map((question) => { const block = paragraphs.get(String(question.config.target_block_id)); return <label key={question.id} {...questionTarget(question, activeQuestionId, "grid gap-2 sm:grid-cols-[1fr_14rem]")}><span className="font-medium"><span className="mr-2 text-[var(--accent)]">{question.number}</span>Paragraph {block?.label ?? "(missing)"}</span><select aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="rounded-md border border-[var(--line)] px-3 py-2"><option value="">Choose heading</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></label>; })}</div></div>;
}

export function MatchingInformationRenderer({ group, values, disabled, onAnswer, passageBlocks = [], highlighting, activeQuestionId }: RendererProps) {
  const paragraphs = passageBlocks.filter((block) => block.type === "paragraph");
  return <div className="space-y-4">{group.questions.map((question) => <div key={question.id} {...questionTarget(question, activeQuestionId, "grid gap-2 sm:grid-cols-[1fr_14rem]")}><QuestionHeader question={question} highlighting={highlighting} /><select aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="select-field"><option value="">Choose paragraph</option>{paragraphs.map((block) => <option key={block.id} value={block.id}>{block.label ?? "Paragraph"}</option>)}</select></div>)}</div>;
}

export function SummaryWordListRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  const layout = group.config as unknown as TextCompletionLayout;
  const options = group.config.options as Option[];
  return <div><ol className="matching-heading-options">{options.map((option) => <li key={option.id}><b>{option.label}.</b> {option.text}</li>)}</ol><div className={`text-completion-layout text-completion-${layout.mode.toLowerCase()}`}>{layout.mode === "PASSAGE" && layout.title?.trim() ? <h3 className="completion-content-title">{layout.title.trim()}</h3> : null}{layout.blocks.map((block) => <div key={block.id} className="text-completion-block text-completion-line">{block.segments.map((segment) => { if (segment.type === "TEXT") return <SelectableText key={segment.id} text={segment.text ?? ""} target={{ target_kind: "TEXT_COMPLETION_SEGMENT", target_id: group.id, segment_id: segment.id }} controller={highlighting} />; const question = group.questions.find((item) => item.id === segment.question_id); return question ? <label key={segment.id} {...questionTarget(question, activeQuestionId, "completion-gap-inline")}><span className="completion-gap-number">{question.number}</span><select aria-label={`Question ${question.number}`} disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="completion-gap-input"><option value="">Choose</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></label> : null; })}</div>)}</div></div>;
}
