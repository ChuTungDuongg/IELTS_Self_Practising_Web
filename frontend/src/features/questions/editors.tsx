"use client";

import type { Option, QuestionGroupModel, QuestionModel } from "./types";

export type EditorProps = {
  group: QuestionGroupModel;
  onChange: (group: QuestionGroupModel) => void;
};

function updateQuestion(
  group: QuestionGroupModel,
  index: number,
  patch: Partial<QuestionModel>,
): QuestionGroupModel {
  const questions = [...group.questions];
  questions[index] = { ...questions[index], ...patch };
  return { ...group, questions };
}

function QuestionActions({ group, index, onChange }: EditorProps & { index: number }) {
  function move(offset: number) {
    const target = index + offset;
    if (target < 0 || target >= group.questions.length) return;
    const questions = [...group.questions];
    [questions[index], questions[target]] = [questions[target], questions[index]];
    onChange({
      ...group,
      questions: questions.map((item, order_index) => ({ ...item, order_index })),
    });
  }
  return (
    <div className="flex gap-2 text-xs">
      <button type="button" onClick={() => move(-1)} aria-label="Move question up">↑</button>
      <button type="button" onClick={() => move(1)} aria-label="Move question down">↓</button>
      <button
        type="button"
        className="text-red-700"
        onClick={() => onChange({ ...group, questions: group.questions.filter((_, item) => item !== index) })}
      >
        Remove
      </button>
    </div>
  );
}

function QuestionFrame({
  group,
  index,
  onChange,
  children,
}: EditorProps & { index: number; children: React.ReactNode }) {
  const question = group.questions[index];
  return (
    <fieldset className="rounded-lg border border-[var(--line)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <legend className="font-semibold">Question {question.number}</legend>
        <QuestionActions group={group} index={index} onChange={onChange} />
      </div>
      <label className="block text-sm">
        Prompt
        <input
          value={question.prompt}
          onChange={(event) => onChange(updateQuestion(group, index, { prompt: event.target.value }))}
          className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2"
        />
      </label>
      {children}
    </fieldset>
  );
}

export function MultipleChoiceEditor(props: EditorProps) {
  const { group, onChange } = props;
  return (
    <div className="space-y-4">
      {group.questions.map((question, index) => {
        const options = question.config.options as Option[];
        const accepted = question.answer_key.accepted as string[];
        function setOptions(next: Option[]) {
          onChange(updateQuestion(group, index, { config: { options: next } }));
        }
        return (
          <QuestionFrame key={question.id ?? index} {...props} index={index}>
            <div className="mt-3 space-y-2">
              {options.map((option, optionIndex) => (
                <div key={option.id} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`key-${index}`}
                    checked={accepted[0] === option.id}
                    onChange={() => onChange(updateQuestion(group, index, { answer_key: { type: "single_choice", accepted: [option.id] } }))}
                    aria-label={`Mark ${option.id} correct`}
                  />
                  <span className="w-6 font-semibold">{option.id}.</span>
                  <input
                    value={option.label}
                    onChange={(event) => setOptions(options.map((item, itemIndex) => itemIndex === optionIndex ? { ...item, label: event.target.value } : item))}
                    className="flex-1 rounded-md border border-[var(--line)] px-3 py-2"
                  />
                </div>
              ))}
              <button type="button" className="text-sm font-semibold text-[var(--accent)]" onClick={() => {
                const id = String.fromCharCode(65 + options.length);
                setOptions([...options, { id, label: "New option" }]);
              }}>+ Add option</button>
            </div>
          </QuestionFrame>
        );
      })}
    </div>
  );
}

const TFNG = ["TRUE", "FALSE", "NOT_GIVEN"] as const;

export function TrueFalseNotGivenEditor(props: EditorProps) {
  const { group, onChange } = props;
  return (
    <div className="space-y-4">
      {group.questions.map((question, index) => (
        <QuestionFrame key={question.id ?? index} {...props} index={index}>
          <div className="mt-3 flex flex-wrap gap-4 text-sm">
            {TFNG.map((value) => (
              <label key={value} className="flex items-center gap-2">
                <input type="radio" name={`tfng-${index}`} checked={(question.answer_key.accepted as string[])[0] === value} onChange={() => onChange(updateQuestion(group, index, { answer_key: { type: "single_choice", accepted: [value] } }))} />
                {value.replace("_", " ")}
              </label>
            ))}
          </div>
        </QuestionFrame>
      ))}
    </div>
  );
}

export function TextCompletionEditor(props: EditorProps) {
  const { group, onChange } = props;
  return (
    <div className="space-y-4">
      {group.questions.map((question, index) => (
        <QuestionFrame key={question.id ?? index} {...props} index={index}>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm sm:col-span-2">Accepted answers, separated by commas
              <input value={(question.answer_key.accepted as string[]).join(", ")} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { type: "text", accepted: event.target.value.split(",").map((item) => item.trim()).filter(Boolean), case_sensitive: false } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" />
            </label>
            <label className="text-sm">Maximum words
              <input type="number" min={1} value={(question.config.max_words as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_words: event.target.value ? Number(event.target.value) : null } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" />
            </label>
            <label className="text-sm">Maximum numbers
              <input type="number" min={0} value={(question.config.max_numbers as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_numbers: event.target.value ? Number(event.target.value) : null } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" />
            </label>
          </div>
        </QuestionFrame>
      ))}
    </div>
  );
}

export function MatchingHeadingsEditor(props: EditorProps) {
  const { group, onChange } = props;
  const options = group.config.options as Option[];
  return (
    <div className="space-y-5">
      <fieldset className="rounded-lg border border-[var(--line)] p-4">
        <legend className="font-semibold">Heading list</legend>
        <div className="mt-2 space-y-2">
          {options.map((option, index) => (
            <div key={option.id} className="flex gap-2"><input value={option.id} onChange={(event) => onChange({ ...group, config: { ...group.config, options: options.map((item, itemIndex) => itemIndex === index ? { ...item, id: event.target.value } : item) } })} className="w-20 rounded-md border border-[var(--line)] px-2 py-1" /><input value={option.label} onChange={(event) => onChange({ ...group, config: { ...group.config, options: options.map((item, itemIndex) => itemIndex === index ? { ...item, label: event.target.value } : item) } })} className="flex-1 rounded-md border border-[var(--line)] px-3 py-1" /></div>
          ))}
          <button type="button" className="text-sm font-semibold text-[var(--accent)]" onClick={() => onChange({ ...group, config: { ...group.config, options: [...options, { id: String(options.length + 1), label: "New heading" }] } })}>+ Add heading</button>
        </div>
      </fieldset>
      {group.questions.map((question, index) => (
        <QuestionFrame key={question.id ?? index} {...props} index={index}>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm">Paragraph target
              <input value={String(question.config.target_label ?? "")} onChange={(event) => onChange(updateQuestion(group, index, { config: { target_label: event.target.value } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2" />
            </label>
            <label className="text-sm">Correct heading
              <select value={(question.answer_key.accepted as string[])[0]} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { type: "single_choice", accepted: [event.target.value] } }))} className="mt-1 w-full rounded-md border border-[var(--line)] px-3 py-2">
                {options.map((option) => <option key={option.id} value={option.id}>{option.id} — {option.label}</option>)}
              </select>
            </label>
          </div>
        </QuestionFrame>
      ))}
    </div>
  );
}
