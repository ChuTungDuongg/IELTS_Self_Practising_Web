"use client";

import { useRef, useState } from "react";
import type { Option, PassageBlock, QuestionGroupModel, QuestionModel, TextCompletionLayout, TextCompletionSegment } from "./types";
import { assetContentUrl } from "@/lib/api/assets";

/* eslint-disable @next/next/no-img-element -- builder previews preserve uploaded image aspect ratios */

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
    const removedId = group.questions[index].id;
    const config = { ...group.config };
    if (Array.isArray(config.markers)) config.markers = (config.markers as Array<{ question_id: string }>).filter((item) => item.question_id !== removedId);
    const layout = config.layout as { rows?: Array<{ cells: Array<{ question_id?: string }> }>; nodes?: Array<{ question_id?: string }> } | undefined;
    if (layout) config.layout = {
      ...layout,
      rows: layout.rows?.filter((row) => !row.cells.some((cell) => cell.question_id === removedId)),
      nodes: layout.nodes?.filter((node) => node.question_id !== removedId),
    };
    onChange({ ...group, config, questions });
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

export function MultipleChoiceMultipleEditor(props: EditorProps) {
  const { group, onChange } = props;
  return <div className="space-y-4">{group.questions.map((question, index) => {
    const options = question.config.options as Option[];
    const selected = new Set((question.answer_key.values as string[] | undefined) ?? []);
    const setOptions = (next: Option[]) => onChange(updateQuestion(group, index, { config: { ...question.config, options: next } }));
    return <QuestionFrame key={question.id} {...props} index={index}><p className="answer-key-label">Select every correct answer</p><div className="option-editor-list">{options.map((option, optionIndex) => <div key={option.id} className={`option-editor-row ${selected.has(option.id) ? "option-editor-correct" : ""}`}><input type="checkbox" checked={selected.has(option.id)} onChange={() => { const next = selected.has(option.id) ? [...selected].filter((id) => id !== option.id) : [...selected, option.id]; onChange(updateQuestion(group, index, { answer_key: { kind: "MULTIPLE_OPTIONS", values: next, order_matters: false } })); }} aria-label={`Mark ${option.label} correct`} /><input value={option.label} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} label`} className="field option-label-field" /><input value={option.text} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} aria-label={`Option ${optionIndex + 1} text`} className="field" /></div>)}</div><button type="button" className="btn btn-secondary mt-3" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: String.fromCharCode(65 + options.length), text: "New option" }])}>+ Add option</button></QuestionFrame>;
  })}</div>;
}

export function MatchingEditor(props: EditorProps) {
  const { group, onChange } = props;
  const options = group.config.options as Option[];
  const setOptions = (next: Option[]) => onChange({ ...group, config: { ...group.config, options: next } });
  return <div className="matching-editor"><section className="matching-section"><div className="matching-section-title"><div><h3>Matching options</h3><p>Stable option IDs remain unchanged when labels are edited.</p></div></div><div className="heading-editor-list">{options.map((option, index) => <div key={option.id} className="heading-editor-row"><input className="field heading-label-field" value={option.label} aria-label={`Matching option ${index + 1} label`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, label: event.target.value } : item))} /><input className="field" value={option.text} aria-label={`Matching option ${index + 1} text`} onChange={(event) => setOptions(options.map((item) => item.id === option.id ? { ...item, text: event.target.value } : item))} /></div>)}</div><button type="button" className="btn btn-secondary mt-3" onClick={() => setOptions([...options, { id: crypto.randomUUID(), label: String.fromCharCode(65 + options.length), text: "New option" }])}>+ Add option</button></section><section className="matching-section"><div className="matching-section-title"><div><h3>Assignments</h3><p>Choose the correct option for each numbered prompt.</p></div></div>{group.questions.map((question, index) => <QuestionFrame key={question.id} {...props} index={index}><label className="field-label">Correct option<select className="select-field" value={singleOptionValue(question)} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(event.target.value) }))}>{options.map((option) => <option key={option.id} value={option.id}>{option.label} — {option.text}</option>)}</select></label></QuestionFrame>)}</section></div>;
}

export function VisualLabellingEditor(props: EditorProps) {
  const { group, onChange } = props;
  const markers = group.config.markers as Array<{ id: string; question_id: string; x: number; y: number }>;
  const [selected, setSelected] = useState(markers[0]?.id ?? "");
  return <div className="space-y-4">{group.image_asset ? <div className="visual-marker-editor"><img src={assetContentUrl(group.image_asset)} alt="Plan, map, or diagram" />{markers.map((marker) => { const question = group.questions.find((item) => item.id === marker.question_id); return <button type="button" key={marker.id} aria-label={`Select marker ${question?.number ?? ""}`} className={`visual-marker ${selected === marker.id ? "visual-marker-selected" : ""}`} style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }} onClick={() => setSelected(marker.id)} title="Select, then click the image to reposition">{question?.number ?? "?"}</button>; })}<button type="button" className="visual-marker-hitarea" aria-label="Place selected marker" onClick={(event) => { const rect = event.currentTarget.getBoundingClientRect(); onChange({ ...group, config: { ...group.config, markers: markers.map((item) => item.id === selected ? { ...item, x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height } : item) } }); }} /></div> : <p className="notice">Upload a PNG, JPEG, or WEBP image above before placing markers.</p>}<MatchingEditor {...props} /></div>;
}

export function StructuredCompletionEditor(props: EditorProps) {
  const { group, onChange } = props;
  const layout = group.config.layout as { kind: string; columns?: Array<{ id: string; label: string }>; rows?: Array<{ id: string; cells: Array<{ id: string; type: "TEXT" | "GAP"; text: string; question_id?: string }> }>; nodes?: Array<{ id: string; type: "TEXT" | "GAP"; text: string; question_id?: string; level: number }> };
  const setLayout = (next: typeof layout) => onChange({ ...group, config: { ...group.config, layout: next } });
  function removeQuestionIds(ids: Set<string>) { return group.questions.filter((question) => !ids.has(question.id ?? "")).map((question, order_index) => ({ ...question, order_index })); }
  return <div className="space-y-4"><section className="matching-section"><div className="matching-section-title"><div><h3>{layout.kind.replace("_", " ")} layout</h3><p>Each gap is linked to one stable question UUID.</p></div></div>{layout.kind === "TABLE" ? <div className="structured-table"><div className="structured-row">{layout.columns?.map((column, columnIndex) => <div key={column.id} className="structured-column"><input className="field" value={column.label} onChange={(event) => setLayout({ ...layout, columns: layout.columns?.map((item) => item.id === column.id ? { ...item, label: event.target.value } : item) })} />{(layout.columns?.length ?? 0) > 1 ? <button type="button" className="icon-button" aria-label={`Remove column ${columnIndex + 1}`} onClick={() => { const removed = new Set(layout.rows?.map((row) => row.cells[columnIndex]?.question_id).filter(Boolean) as string[]); onChange({ ...group, questions: removeQuestionIds(removed), config: { ...group.config, layout: { ...layout, columns: layout.columns?.filter((item) => item.id !== column.id), rows: layout.rows?.map((row) => ({ ...row, cells: row.cells.filter((_, index) => index !== columnIndex) })) } } }); }}>×</button> : null}</div>)}</div>{layout.rows?.map((row) => <div key={row.id} className="structured-row-wrap"><div className="structured-row">{row.cells.map((cell) => cell.type === "GAP" ? <span key={cell.id} className="structured-gap">Q{group.questions.find((item) => item.id === cell.question_id)?.number ?? "?"}</span> : <input key={cell.id} className="field" value={cell.text} onChange={(event) => setLayout({ ...layout, rows: layout.rows?.map((item) => item.id === row.id ? { ...item, cells: item.cells.map((entry) => entry.id === cell.id ? { ...entry, text: event.target.value } : entry) } : item) })} />)}</div><button type="button" className="btn btn-danger-ghost" onClick={() => { const removed = new Set(row.cells.map((cell) => cell.question_id).filter(Boolean) as string[]); onChange({ ...group, questions: removeQuestionIds(removed), config: { ...group.config, layout: { ...layout, rows: layout.rows?.filter((item) => item.id !== row.id) } } }); }}>Remove row</button></div>)}<div className="flex flex-wrap gap-2"><button type="button" className="btn btn-secondary" onClick={() => setLayout({ ...layout, columns: [...(layout.columns ?? []), { id: crypto.randomUUID(), label: "Column" }], rows: layout.rows?.map((row) => ({ ...row, cells: [...row.cells, { id: crypto.randomUUID(), type: "TEXT", text: "Text" }] })) })}>+ Add column</button><button type="button" className="btn btn-secondary" onClick={() => setLayout({ ...layout, rows: [...(layout.rows ?? []), { id: crypto.randomUUID(), cells: (layout.columns ?? []).map(() => ({ id: crypto.randomUUID(), type: "TEXT", text: "Text" })) }] })}>+ Add row</button></div></div> : <div className="structured-node-list">{layout.nodes?.map((node) => <div key={node.id} className="structured-node">{node.type === "GAP" ? <span className="structured-gap">Gap · Q{group.questions.find((item) => item.id === node.question_id)?.number ?? "?"}</span> : <input className="field" value={node.text} onChange={(event) => setLayout({ ...layout, nodes: layout.nodes?.map((item) => item.id === node.id ? { ...item, text: event.target.value } : item) })} />}<button type="button" className="icon-button" aria-label="Remove layout node" onClick={() => { const removed = new Set(node.question_id ? [node.question_id] : []); onChange({ ...group, questions: removeQuestionIds(removed), config: { ...group.config, layout: { ...layout, nodes: layout.nodes?.filter((item) => item.id !== node.id) } } }); }}>×</button></div>)}<button type="button" className="btn btn-secondary" onClick={() => setLayout({ ...layout, nodes: [...(layout.nodes ?? []), { id: crypto.randomUUID(), type: "TEXT", text: "Text", level: 0 }] })}>+ Add text block</button></div>}</section><TextCompletionEditor {...props} /></div>;
}

const TFNG = ["TRUE", "FALSE", "NOT_GIVEN"] as const;
const YNNG = ["YES", "NO", "NOT_GIVEN"] as const;

export function TrueFalseNotGivenEditor(props: EditorProps) {
  return <AgreementEditor {...props} values={TFNG} name="tfng" />;
}

export function YesNoNotGivenEditor(props: EditorProps) {
  return <AgreementEditor {...props} values={YNNG} name="ynng" />;
}

function AgreementEditor({ values, name, ...props }: EditorProps & { values: readonly string[]; name: string }) {
  const { group, onChange } = props;
  return (
    <div className="space-y-4">
      {group.questions.map((question, index) => (
        <QuestionFrame key={question.id} {...props} index={index}>
          <div className="answer-choice-row">
            {values.map((value) => <label key={value} className={singleOptionValue(question) === value ? "selected" : ""}><input type="radio" name={`${name}-${question.id}`} checked={singleOptionValue(question) === value} onChange={() => onChange(updateQuestion(group, index, { answer_key: singleOptionKey(value) }))} />{value.replace("_", " ")}</label>)}
          </div>
        </QuestionFrame>
      ))}
    </div>
  );
}

export function TextCompletionEditor(props: EditorProps) {
  const { group } = props;
  if (group.question_type !== "text_completion") return <TextAnswerEditors {...props} />;
  return <StructuredTextCompletionEditor {...props} />;
}

function normalizeTextCompletionOrder(group: QuestionGroupModel, layout: TextCompletionLayout): QuestionGroupModel {
  const ids = layout.blocks.flatMap((block) => block.segments.filter((segment) => segment.type === "GAP").map((segment) => segment.question_id!));
  const byId = new Map(group.questions.map((question) => [question.id, question]));
  const first = group.questions.length ? Math.min(...group.questions.map((question) => question.number)) : 1;
  return {
    ...group,
    config: layout,
    questions: ids.flatMap((id, order_index) => {
      const question = byId.get(id);
      return question ? [{ ...question, number: first + order_index, order_index }] : [];
    }),
  };
}

function StructuredTextCompletionEditor(props: EditorProps) {
  const { group, onChange } = props;
  const layout = group.config as unknown as TextCompletionLayout;
  const active = useRef<{ segmentId: string; offset: number } | null>(null);

  function commit(nextLayout: TextCompletionLayout, nextQuestions = group.questions) {
    onChange(normalizeTextCompletionOrder({ ...group, questions: nextQuestions }, nextLayout));
  }

  function updateText(segmentId: string, text: string) {
    commit({ ...layout, blocks: layout.blocks.map((block) => ({ ...block, segments: block.segments.map((segment) => segment.id === segmentId ? { ...segment, text } : segment) })) });
  }

  function insertGap() {
    const targetBlock = layout.blocks.find((block) => block.segments.some((segment) => segment.id === active.current?.segmentId)) ?? layout.blocks.at(-1);
    if (!targetBlock) return;
    const target = targetBlock.segments.find((segment) => segment.id === active.current?.segmentId && segment.type === "TEXT") ?? [...targetBlock.segments].reverse().find((segment) => segment.type === "TEXT");
    const questionId = crypto.randomUUID();
    const nextNumber = Math.max(0, ...group.questions.map((question) => question.number)) + 1;
    const question: QuestionModel = { id: questionId, number: nextNumber, prompt: "Answer", config: { max_words: 2, max_numbers: 1 }, answer_key: { kind: "TEXT", accepted: ["answer"], case_sensitive: false }, order_index: group.questions.length };
    const gap: TextCompletionSegment = { id: crypto.randomUUID(), type: "GAP", question_id: questionId };
    const blocks = layout.blocks.map((block) => {
      if (block.id !== targetBlock.id) return block;
      if (!target) return { ...block, segments: [...block.segments, gap] };
      const offset = active.current?.segmentId === target.id ? Math.max(0, Math.min(active.current.offset, target.text?.length ?? 0)) : target.text?.length ?? 0;
      const segments = block.segments.flatMap((segment) => segment.id !== target.id ? [segment] : [
        { ...segment, text: (segment.text ?? "").slice(0, offset) },
        gap,
        { id: crypto.randomUUID(), type: "TEXT" as const, text: (segment.text ?? "").slice(offset) },
      ]).filter((segment) => segment.type === "GAP" || Boolean(segment.text));
      return { ...block, segments };
    });
    active.current = null;
    commit({ ...layout, blocks }, [...group.questions, question]);
  }

  function removeGap(questionId: string) {
    if (!window.confirm("Remove this gap and its linked question?")) return;
    const blocks = layout.blocks.map((block) => {
      const segments: TextCompletionSegment[] = [];
      for (const segment of block.segments) {
        if (segment.type === "GAP" && segment.question_id === questionId) continue;
        const previous = segments.at(-1);
        if (previous?.type === "TEXT" && segment.type === "TEXT") previous.text = `${previous.text ?? ""}${segment.text ?? ""}`;
        else segments.push({ ...segment });
      }
      return { ...block, segments: segments.length ? segments : [{ id: crypto.randomUUID(), type: "TEXT" as const, text: "" }] };
    });
    commit({ ...layout, blocks }, group.questions.filter((question) => question.id !== questionId));
  }

  function moveBlock(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= layout.blocks.length) return;
    const blocks = [...layout.blocks];
    [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
    commit({ ...layout, blocks });
  }

  return <div className="space-y-5">
    <section className="matching-section">
      <div className="matching-section-title"><div><h3>Completion text</h3><p>Place the caret in a text segment, then insert a stable numbered gap.</p></div><label className="field-label">Mode<select className="select-field" value={layout.mode} onChange={(event) => commit({ ...layout, mode: event.target.value as TextCompletionLayout["mode"] })}><option value="SENTENCE">Sentence</option><option value="PASSAGE">Passage</option></select></label></div>
      <div className="space-y-3">{layout.blocks.map((block, blockIndex) => <div key={block.id} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3"><div className="flex flex-wrap items-center gap-2">{block.segments.map((segment) => segment.type === "GAP" ? <button key={segment.id} type="button" className="structured-gap" onClick={() => removeGap(segment.question_id!)} title="Remove gap">Q{group.questions.find((question) => question.id === segment.question_id)?.number ?? "?"} ×</button> : <textarea key={segment.id} aria-label={`Paragraph ${blockIndex + 1} text segment`} className="field min-h-20 min-w-48 flex-1" value={segment.text ?? ""} onFocus={(event) => { active.current = { segmentId: segment.id, offset: event.currentTarget.selectionStart }; }} onSelect={(event) => { active.current = { segmentId: segment.id, offset: event.currentTarget.selectionStart }; }} onChange={(event) => updateText(segment.id, event.target.value)} />)}</div>{layout.mode === "PASSAGE" ? <div className="mt-2 flex flex-wrap gap-2"><button type="button" className="icon-button" disabled={blockIndex === 0} aria-label={`Move paragraph ${blockIndex + 1} up`} onClick={() => moveBlock(blockIndex, -1)}>↑</button><button type="button" className="icon-button" disabled={blockIndex === layout.blocks.length - 1} aria-label={`Move paragraph ${blockIndex + 1} down`} onClick={() => moveBlock(blockIndex, 1)}>↓</button>{layout.blocks.length > 1 ? <button type="button" className="btn btn-danger-ghost" onClick={() => { if (!window.confirm("Remove this paragraph and all linked gaps?")) return; const removed = new Set(block.segments.filter((segment) => segment.type === "GAP").map((segment) => segment.question_id)); commit({ ...layout, blocks: layout.blocks.filter((item) => item.id !== block.id) }, group.questions.filter((question) => !removed.has(question.id))); }}>Remove paragraph</button> : null}</div> : null}</div>)}</div>
      <div className="mt-3 flex flex-wrap gap-2"><button type="button" className="btn btn-secondary" onClick={insertGap}>+ Insert gap</button>{layout.mode === "PASSAGE" ? <button type="button" className="btn btn-secondary" onClick={() => commit({ ...layout, blocks: [...layout.blocks, { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "New paragraph" }] }] })}>+ Add paragraph</button> : null}</div>
    </section>
    <TextAnswerEditors {...props} group={{ ...group, config: layout }} />
  </div>;
}

function TextAnswerEditors(props: EditorProps) {
  const { group, onChange } = props;
  return (
    <div className="space-y-4">
      {group.questions.map((question, index) => (
        <fieldset key={question.id} className="question-editor-card" aria-label={`Question ${question.number} answer editor`}>
          <div className="question-editor-header"><span className="question-number">Q{question.number}</span><p>Answer key</p></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <label className="field-label sm:col-span-2">Correct answer<input value={String((question.answer_key.accepted as string[] | undefined)?.[0] ?? "")} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { kind: "TEXT", accepted: [event.target.value, ...((question.answer_key.accepted as string[] | undefined) ?? []).slice(1)], case_sensitive: Boolean(question.answer_key.case_sensitive) } }))} className="field" /></label>
            <div className="sm:col-span-2"><p className="field-label">Alternative answers</p>{((question.answer_key.accepted as string[] | undefined) ?? []).slice(1).map((answer, alternativeIndex) => <div key={alternativeIndex} className="mt-2 flex gap-2"><input aria-label={`Alternative answer ${alternativeIndex + 1}`} className="field" value={answer} onChange={(event) => { const accepted = [...(question.answer_key.accepted as string[])]; accepted[alternativeIndex + 1] = event.target.value; onChange(updateQuestion(group, index, { answer_key: { kind: "TEXT", accepted, case_sensitive: Boolean(question.answer_key.case_sensitive) } })); }} /><button type="button" className="btn btn-danger-ghost" onClick={() => onChange(updateQuestion(group, index, { answer_key: { kind: "TEXT", accepted: (question.answer_key.accepted as string[]).filter((_, item) => item !== alternativeIndex + 1), case_sensitive: Boolean(question.answer_key.case_sensitive) } }))}>Remove</button></div>)}<button type="button" className="btn btn-secondary mt-2" onClick={() => onChange(updateQuestion(group, index, { answer_key: { kind: "TEXT", accepted: [...((question.answer_key.accepted as string[] | undefined) ?? []), ""], case_sensitive: Boolean(question.answer_key.case_sensitive) } }))}>+ Add alternative answer</button></div>
            <label className="field-label">Maximum words<input type="number" min={1} value={(question.config.max_words as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_words: event.target.value ? Number(event.target.value) : null } }))} className="field" /></label>
            <label className="field-label">Maximum numbers<input type="number" min={0} value={(question.config.max_numbers as number | undefined) ?? ""} onChange={(event) => onChange(updateQuestion(group, index, { config: { ...question.config, max_numbers: event.target.value ? Number(event.target.value) : null } }))} className="field" /></label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(question.answer_key.case_sensitive)} onChange={(event) => onChange(updateQuestion(group, index, { answer_key: { kind: "TEXT", accepted: question.answer_key.accepted, case_sensitive: event.target.checked } }))} /> Case-sensitive grading</label>
          </div>
        </fieldset>
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
