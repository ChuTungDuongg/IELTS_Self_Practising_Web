"use client";

import type { ExamGroup, ExamQuestion, Option } from "./types";

export type RendererProps = {
  group: ExamGroup;
  values: Record<string, unknown>;
  disabled?: boolean;
  onAnswer?: (questionId: string, value: string) => void;
};

function QuestionHeader({ question }: { question: ExamQuestion }) {
  return <p className="font-medium"><span className="mr-2 text-[var(--accent)]">{question.number}</span>{question.prompt}</p>;
}

export function MultipleChoiceRenderer({ group, values, disabled, onAnswer }: RendererProps) {
  return <div className="space-y-5">{group.questions.map((question) => <fieldset key={question.id}><QuestionHeader question={question} /><div className="mt-2 space-y-2">{(question.config.options as Option[]).map((option) => <label key={option.id} className="flex items-start gap-2"><input type="radio" disabled={disabled} name={question.id} checked={values[question.id] === option.id} onChange={() => onAnswer?.(question.id, option.id)} /><span><b>{option.id}.</b> {option.label}</span></label>)}</div></fieldset>)}</div>;
}

export function TrueFalseNotGivenRenderer({ group, values, disabled, onAnswer }: RendererProps) {
  const choices = ["TRUE", "FALSE", "NOT_GIVEN"];
  return <div className="space-y-5">{group.questions.map((question) => <fieldset key={question.id}><QuestionHeader question={question} /><div className="mt-2 flex flex-wrap gap-4">{choices.map((choice) => <label key={choice} className="flex items-center gap-2"><input type="radio" disabled={disabled} name={question.id} checked={values[question.id] === choice} onChange={() => onAnswer?.(question.id, choice)} />{choice.replace("_", " ")}</label>)}</div></fieldset>)}</div>;
}

export function TextCompletionRenderer({ group, values, disabled, onAnswer }: RendererProps) {
  return <div className="space-y-4">{group.questions.map((question) => <label key={question.id} className="block"><QuestionHeader question={question} /><input disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="mt-2 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label>)}</div>;
}

export function MatchingHeadingsRenderer({ group, values, disabled, onAnswer }: RendererProps) {
  const options = group.config.options as Option[];
  return <div><ol className="mb-5 list-inside list-roman space-y-1 text-sm text-[var(--muted)]">{options.map((option) => <li key={option.id}><b>{option.id}.</b> {option.label}</li>)}</ol><div className="space-y-4">{group.questions.map((question) => <label key={question.id} className="grid gap-2 sm:grid-cols-[1fr_14rem]"><QuestionHeader question={question} /><select disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} className="rounded-md border border-[var(--line)] px-3 py-2"><option value="">Choose heading</option>{options.map((option) => <option key={option.id} value={option.id}>{option.id} — {option.label}</option>)}</select></label>)}</div></div>;
}
