"use client";

import type { Option, PassageBlock, QuestionGroupModel, QuestionModel } from "./types";

export type EditorProps = {
  group: QuestionGroupModel;
  onChange: (group: QuestionGroupModel) => void;
  passageBlocks?: PassageBlock[];
};

function updateQuestion(group: QuestionGroupModel, index: number, patch: Partial<QuestionModel>): QuestionGroupModel {
  const questions = [...group.questions];
  questions[index] = { ...questions[index], ...patch };
  return { ...group, questions };
}

function singleOptionValue(question: QuestionModel): string {
  return String(question.answer_key.value ?? "");
}

function singleOptionKey(value: string): Record<string, unknown> {
  return { kind: "SINGLE_OPTION", value };
}

function QuestionActions({ group, index, onChange }: EditorProps & { index: number }) {
  function move(offset: number) {
    const target = index + offset;
    if (target < 0 || target >= group.questions.length) return;
    const questions = [...group.questions];
    const displayNumbers = questions.map((question) => question.number).sort((a, b) => a - b);
    [questions[index], questions[target]] = [questions[target], questions[index]];
    onChange({ ...group, questions: questions.map((item, order_index) => ({ ...item, number: displayNumbers[order_index], order_index })) });
  }
  function remove() {
    const firstNumber = Math.min(...group.questions.map((question) => question.number));
    const questions = group.questions
      .filter((_, item) => item !== index)
      .map((question, order_index) => ({
        ...question,
        number: firstNumber + order_index,
        order_index,
      }));
    onChange({ ...group, questions });
  }
  return <div className="flex gap-2 text-xs"><button type="button" onClick={() => move(-1)} aria-label="Move question up">↑</button><button type="button" onClick={() => move(1)} aria-label="Move question down">↓</button><button type="button" className="text-red-700" onClick={remove}>Remove</button></div>;
}

function QuestionFrame({ group, index, onChange, children }: EditorProps & { index: number; children: React.ReactNode }) {
  const question = group.questions[index];
  return <fieldset className="rounded-lg border border-[var(--line)] p-4"><div className="mb-3 flex items-center justify-between"><legend className="font-semibold">Question {question.number}</legend><QuestionActions group={group} index={index} onChange={onChange} /></div><label className="block text-sm">Prompt<input value={question.prompt} onChange={(event) => onChange(updateQuestion(group, index, { prompt: event.target.value }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label>{children}</fieldset>;
}

export function MultipleChoiceEditor(props: EditorProps) {
  const { group, onChange } = props;
  return <div className="space-y-4">{group.questions.map((question, index) => {
    const options = question.config.options as Option[];
    const accepted = singleOptionValue(question);
    const setOptions = (next: Option[]) => onChange(updateQuestion(group, index, { config: { options: next } }));
    return <QuestionFrame key={question.id} {...props} index={index}><div className="mt-3 space-y-2">{options.map((option, optionIndex) => <div key={option.id} className="flex items-center gap-2"><input type="radio" name={`key-${question.id}`} checked={accepted === option.id} onChange={() => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(option.id) }))} aria-label={`Mark ${option.label} correct`} /><input value={option.label} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} label`} className="w-20 rounded-md border border-[var(--line)] px-2 py-2 font-semibold" /><input value={option.text} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} text`} className="flex-1 rounded-md border border-[var(--line)] px-3 py-2" /></div>)}<button type="button" className="text-sm font-semibold text-[var(--accent)]" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: String.fromCharCode(65 + options.length), text: "New option" }])}>+ Add option</button></div></QuestionFrame>;
  })}</div>;
}

const TFNG = ["TRUE", "FALSE", "NOT_GIVEN"] as const;

export function TrueFalseNotGivenEditor(props: EditorProps) {
  const { group, onChange } = props;
  return <div className="space-y-4">{group.questions.map((question, index) => <QuestionFrame key={question.id} {...props} index={index}><div className="mt-3 flex flex-wrap gap-4 text-sm">{TFNG.map((value) => <label key={value} className="flex items-center gap-2"><input type="radio" name={`tfng-${question.id}`} checked={singleOptionValue(question) === value} onChange={() => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(value) }))} />{value.replace("_", " ")}</label>)}</div></QuestionFrame>)}</div>;
}

export function TextCompletionEditor(props: EditorProps) {
  const { group, onChange } = props;
  return <div className="space-y-4">{group.questions.map((question, index) => <QuestionFrame key={question.id} {...props} index={index}><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="text-sm sm:col-span-2">Accepted answers, separated by commas<input value={(question.answer_key.accepted as string[]).join(", ")} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { type: "text", accepted: event.target.value.split(",").map((item) => item.trim()).filter(Boolean), case_sensitive: false } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label><label className="text-sm">Maximum words<input type="number" min={1} value={(question.config.max_words as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_words: event.target.value ? Number(event.target.value) : null } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label><label className="text-sm">Maximum numbers<input type="number" min={0} value={(question.config.max_numbers as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_numbers: event.target.value ? Number(event.target.value) : null } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" /></label></div></QuestionFrame>)}</div>;
}

export function MatchingHeadingsEditor(props: EditorProps) {
  const { group, onChange, passageBlocks = [] } = props;
  const options = group.config.options as Option[];
  const paragraphs = passageBlocks.filter((block) => block.type === "paragraph");
  const duplicateLabels = duplicateValues(options.map((option) => option.label));
  const setOptions = (next: Option[]) => onChange({ ...group, config: { ...group.config, options: next } });
  function moveOption(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= options.length) return;
    const next = [...options];
    [next[index], next[target]] = [next[target], next[index]];
    setOptions(next);
  }
  return <div className="space-y-5"><fieldset className="rounded-lg border border-[var(--line)] p-4"><legend className="font-semibold">Headings</legend>{duplicateLabels.length ? <p role="alert" className="mt-2 text-sm text-red-700">Duplicate heading labels: {duplicateLabels.join(", ")}. Labels must be unique before publishing.</p> : null}<div className="mt-2 space-y-2">{options.map((option, index) => { const references = headingReferences(group, option.id); return <div key={option.id} className="flex flex-wrap items-center gap-2"><input value={option.label} aria-label={`Heading ${index + 1} label`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} className="w-20 rounded-md border border-[var(--line)] px-2 py-1 font-semibold" /><input value={option.text} aria-label={`Heading ${index + 1} text`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} className="min-w-64 flex-1 rounded-md border border-[var(--line)] px-3 py-1" /><button type="button" onClick={() => moveOption(index, -1)} aria-label={`Move heading ${option.label} up`}>↑</button><button type="button" onClick={() => moveOption(index, 1)} aria-label={`Move heading ${option.label} down`}>↓</button><button type="button" disabled={references.length > 0} title={references.length ? `Used by Q${references.join(", Q")}` : "Remove heading"} className="text-sm text-red-700 disabled:cursor-not-allowed disabled:opacity-50" onClick={() => setOptions(options.filter((item) => item.id !== option.id))}>Remove</button>{references.length ? <span className="text-xs text-amber-700">Used by Q{references.join(", Q")}</span> : null}</div>; })}<button type="button" className="text-sm font-semibold text-[var(--accent)]" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: toRoman(options.length + 1), text: "New heading" }])}>+ Add heading</button></div></fieldset><h3 className="font-semibold">Paragraph assignments</h3>{group.questions.map((question, index) => <fieldset key={question.id} className="rounded-lg border border-[var(--line)] p-4"><div className="grid items-end gap-3 sm:grid-cols-[auto_1fr_1fr_auto]"><legend className="self-center font-semibold">Q{question.number}</legend><label className="text-sm">Paragraph<select aria-label={`Question ${question.number} paragraph`} value={String(question.config.target_block_id ?? "")} onChange={(event) => onChange(updateQuestion(group, index, { config: { target_block_id: event.target.value } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2"><option value="">Choose paragraph</option>{paragraphs.map((block) => <option key={block.id} value={block.id}>{block.label} — {excerpt(block.text)}</option>)}</select></label><label className="text-sm">Correct heading<select aria-label={`Question ${question.number} correct heading`} value={singleOptionValue(question)} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(event.target.value) }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2"><option value="">Choose heading</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></label><QuestionActions group={group} index={index} onChange={onChange} /></div>{!paragraphs.some((block) => block.id === question.config.target_block_id) ? <p role="alert" className="mt-2 text-sm text-red-700">This assignment references a missing paragraph. Choose a current passage paragraph.</p> : null}{!options.some((option) => option.id === singleOptionValue(question)) ? <p role="alert" className="mt-2 text-sm text-red-700">This assignment references a missing heading. Choose a current heading.</p> : null}</fieldset>)}</div>;
}

function headingReferences(group: QuestionGroupModel, optionId: string): number[] {
  return group.questions.filter((question) => singleOptionValue(question) === optionId).map((question) => question.number);
}

function duplicateValues(values: string[]): string[] {
  const normalized = values.map((value) => value.trim().toLocaleLowerCase());
  return values.filter((_, index) => normalized.indexOf(normalized[index]) !== index);
}

function excerpt(text: string): string {
  return text.length > 55 ? `${text.slice(0, 52)}…` : text;
}

function toRoman(value: number): string {
  const numerals: Array<[number, string]> = [[1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"], [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]];
  let remaining = value;
  return numerals.reduce((result, [amount, symbol]) => { while (remaining >= amount) { result += symbol; remaining -= amount; } return result; }, "");
}
