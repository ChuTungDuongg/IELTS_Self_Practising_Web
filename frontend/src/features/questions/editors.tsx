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
      .map((question, order_index) => ({ ...question, number: firstNumber + order_index, order_index }));
    onChange({ ...group, questions });
  }

  return (
    <div className="question-actions">
      <button type="button" onClick={() => move(-1)} aria-label="Move question up" className="icon-button">↑</button>
      <button type="button" onClick={() => move(1)} aria-label="Move question down" className="icon-button">↓</button>
      <button type="button" className="btn btn-danger-ghost" onClick={remove}>Remove</button>
    </div>
  );
}

function QuestionFrame({ group, index, onChange, children }: EditorProps & { index: number; children: React.ReactNode }) {
  const question = group.questions[index];
  return (
    <fieldset className="question-editor-card" aria-label={`Question ${question.number} editor`}>
      <div className="question-editor-header">
        <span className="question-number">Q{question.number}</span>
        <p>Question {question.number}</p>
        <QuestionActions group={group} index={index} onChange={onChange} />
      </div>
      <label className="field-label">Prompt<input value={question.prompt} onChange={(event) => onChange(updateQuestion(group, index, { prompt: event.target.value }))} className="field" /></label>
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
        const accepted = singleOptionValue(question);
        const setOptions = (next: Option[]) => onChange(updateQuestion(group, index, { config: { options: next } }));
        return (
          <QuestionFrame key={question.id} {...props} index={index}>
            <div className="option-editor-list">
              <p className="answer-key-label">Select the correct answer</p>
              {options.map((option, optionIndex) => (
                <div key={option.id} className={`option-editor-row ${accepted === option.id ? "option-editor-correct" : ""}`}>
                  <input type="radio" name={`key-${question.id}`} checked={accepted === option.id} onChange={() => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(option.id) }))} aria-label={`Mark ${option.label} correct`} />
                  <input value={option.label} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} label`} className="field option-label-field" />
                  <input value={option.text} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} text`} className="field" />
                </div>
              ))}
              <button type="button" className="btn btn-secondary mt-1" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: String.fromCharCode(65 + options.length), text: "New option" }])}>+ Add option</button>
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
        <QuestionFrame key={question.id} {...props} index={index}>
          <div className="answer-choice-row">
            {TFNG.map((value) => <label key={value} className={singleOptionValue(question) === value ? "selected" : ""}><input type="radio" name={`tfng-${question.id}`} checked={singleOptionValue(question) === value} onChange={() => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(value) }))} />{value.replace("_", " ")}</label>)}
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
        <QuestionFrame key={question.id} {...props} index={index}>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="field-label sm:col-span-2">Accepted answers, separated by commas<input value={(question.answer_key.accepted as string[]).join(", ")} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { type: "text", accepted: event.target.value.split(",").map((item) => item.trim()).filter(Boolean), case_sensitive: false } }))} className="field" /></label>
            <label className="field-label">Maximum words<input type="number" min={1} value={(question.config.max_words as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_words: event.target.value ? Number(event.target.value) : null } }))} className="field" /></label>
            <label className="field-label">Maximum numbers<input type="number" min={0} value={(question.config.max_numbers as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_numbers: event.target.value ? Number(event.target.value) : null } }))} className="field" /></label>
          </div>
        </QuestionFrame>
      ))}
    </div>
  );
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

  return (
    <div className="matching-editor">
      <section className="matching-section" aria-labelledby="headings-title">
        <div className="matching-section-title"><div><h3 id="headings-title">Headings</h3><p>These choices are referenced by stable IDs, so reordering is safe.</p></div><span>{options.length} headings</span></div>
        {duplicateLabels.length ? <p role="alert" className="notice notice-error mt-3">Duplicate heading labels: {duplicateLabels.join(", ")}. Labels must be unique before publishing.</p> : null}
        <div className="heading-editor-list">
          {options.map((option, index) => {
            const references = headingReferences(group, option.id);
            return (
              <div key={option.id} className="heading-editor-row">
                <input value={option.label} aria-label={`Heading ${index + 1} label`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} className="field heading-label-field" />
                <input value={option.text} aria-label={`Heading ${index + 1} text`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} className="field" />
                <button type="button" onClick={() => moveOption(index, -1)} aria-label={`Move heading ${option.label} up`} className="icon-button">↑</button>
                <button type="button" onClick={() => moveOption(index, 1)} aria-label={`Move heading ${option.label} down`} className="icon-button">↓</button>
                <button type="button" disabled={references.length > 0} title={references.length ? `Used by Q${references.join(", Q")}` : "Remove heading"} className="btn btn-danger-ghost" onClick={() => setOptions(options.filter((item) => item.id !== option.id))}>Remove</button>
                {references.length ? <span className="heading-reference">Used by Q{references.join(", Q")}</span> : null}
              </div>
            );
          })}
        </div>
        <button type="button" className="btn btn-secondary mt-3" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: toRoman(options.length + 1), text: "New heading" }])}>+ Add heading</button>
      </section>

      <section className="matching-section" aria-labelledby="assignments-title">
        <div className="matching-section-title"><div><h3 id="assignments-title">Assignments</h3><p>Connect each numbered question to one passage paragraph and its correct heading.</p></div><span>{group.questions.length} questions</span></div>
        <div className="assignment-list">
          {group.questions.map((question, index) => {
            const missingParagraph = !paragraphs.some((block) => block.id === question.config.target_block_id);
            const missingHeading = !options.some((option) => option.id === singleOptionValue(question));
            return (
              <fieldset key={question.id} className={`assignment-row ${missingParagraph || missingHeading ? "assignment-invalid" : ""}`}>
                <legend className="sr-only">Question {question.number} assignment</legend>
                <span className="question-number">Q{question.number}</span>
                <label className="field-label">Paragraph<select aria-label={`Question ${question.number} paragraph`} value={String(question.config.target_block_id ?? "")} onChange={(event) => onChange(updateQuestion(group, index, { config: { target_block_id: event.target.value } }))} className="select-field"><option value="">Choose paragraph</option>{paragraphs.map((block) => <option key={block.id} value={block.id}>{block.label} — {excerpt(block.text)}</option>)}</select></label>
                <label className="field-label">Correct heading<select aria-label={`Question ${question.number} correct heading`} value={singleOptionValue(question)} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(event.target.value) }))} className="select-field"><option value="">Choose heading</option>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></label>
                <QuestionActions group={group} index={index} onChange={onChange} />
                {missingParagraph ? <p role="alert" className="assignment-error">Missing paragraph reference. Choose a current passage paragraph.</p> : null}
                {missingHeading ? <p role="alert" className="assignment-error">Missing heading reference. Choose a current heading.</p> : null}
              </fieldset>
            );
          })}
        </div>
      </section>
    </div>
  );
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
  return numerals.reduce((result, [amount, symbol]) => {
    while (remaining >= amount) {
      result += symbol;
      remaining -= amount;
    }
    return result;
  }, "");
}
