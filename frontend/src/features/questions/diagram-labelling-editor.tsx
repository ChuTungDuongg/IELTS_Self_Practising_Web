"use client";

import { useRef, useState } from "react";
import { assetContentUrl } from "@/lib/api/assets";
import type { EditorProps } from "./editors";
import {
  DIAGRAM_MAX_WIDTH,
  DIAGRAM_MIN_WIDTH,
  createDiagramCanvasItem,
  diagramPercent,
  diagramLabellingErrors,
  splitDiagramPrompt,
} from "./diagram-labelling";
import type { DiagramCanvasItem, DiagramLabellingConfig, QuestionGroupModel, QuestionModel } from "./types";

/* eslint-disable @next/next/no-img-element -- the authored canvas must preserve the source aspect ratio */

type DragState = {
  kind: "box" | "start" | "end";
  item: DiagramCanvasItem;
  pointerId: number;
  pointerX: number;
  pointerY: number;
  maxY: number;
};

export function DiagramLabellingEditor({ group, onChange, baseQuestionNumber }: EditorProps) {
  const config = group.config as unknown as DiagramLabellingConfig;
  const items = config.items ?? [];
  const [selectedId, setSelectedId] = useState(items[0]?.id ?? "");
  const [drag, setDrag] = useState<DragState | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  const selectedItem = items.find((item) => item.id === selectedId) ?? items[0];
  const selectedQuestionIndex = group.questions.findIndex(
    (question) => question.id === selectedItem?.question_id,
  );
  const selectedQuestion = group.questions[selectedQuestionIndex];

  function setItems(next: DiagramCanvasItem[]) {
    onChange({ ...group, config: { items: next } });
  }

  function updateItem(itemId: string, update: (item: DiagramCanvasItem) => DiagramCanvasItem) {
    setItems(items.map((item) => item.id === itemId ? update(item) : item));
  }

  function updateQuestion(patch: Partial<QuestionModel>) {
    if (selectedQuestionIndex < 0) return;
    const questions = [...group.questions];
    questions[selectedQuestionIndex] = { ...questions[selectedQuestionIndex], ...patch };
    onChange({ ...group, questions });
  }

  function beginDrag(
    event: React.PointerEvent<HTMLElement>,
    item: DiagramCanvasItem,
    kind: DragState["kind"],
  ) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const canvasRect = canvas.getBoundingClientRect();
    const label = canvas.querySelector<HTMLElement>(`[data-diagram-item-id="${item.id}"]`);
    const labelHeight = label ? label.getBoundingClientRect().height / canvasRect.height : 0.1;
    setSelectedId(item.id);
    setDrag({
      kind,
      item,
      pointerId: event.pointerId,
      pointerX: event.clientX,
      pointerY: event.clientY,
      maxY: Math.max(0, 1 - labelHeight),
    });
  }

  function moveDrag(event: React.PointerEvent<HTMLElement>) {
    if (!drag || event.pointerId !== drag.pointerId || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    event.preventDefault();
    const dx = (event.clientX - drag.pointerX) / rect.width;
    const dy = (event.clientY - drag.pointerY) / rect.height;
    updateItem(drag.item.id, (current) => {
      if (drag.kind === "box") {
        const x = clamp(drag.item.box.x + dx, 0, 1 - drag.item.box.width);
        const y = clamp(drag.item.box.y + dy, 0, drag.maxY);
        const actualDx = x - drag.item.box.x;
        const actualDy = y - drag.item.box.y;
        return {
          ...current,
          box: { ...current.box, x, y },
          arrow: {
            ...current.arrow,
            start_x: clamp(drag.item.arrow.start_x + actualDx),
            start_y: clamp(drag.item.arrow.start_y + actualDy),
          },
        };
      }
      const point = {
        x: clamp((event.clientX - rect.left) / rect.width),
        y: clamp((event.clientY - rect.top) / rect.height),
      };
      return drag.kind === "start"
        ? { ...current, arrow: { ...current.arrow, start_x: point.x, start_y: point.y } }
        : { ...current, arrow: { ...current.arrow, end_x: point.x, end_y: point.y } };
    });
  }

  function endDrag(event: React.PointerEvent<HTMLElement>) {
    if (drag?.pointerId === event.pointerId) setDrag(null);
  }

  function removeSelected() {
    if (!selectedItem) return;
    const firstNumber = Math.min(...group.questions.map((question) => question.number));
    const questions = group.questions
      .filter((question) => question.id !== selectedItem.question_id)
      .map((question, order_index) => ({ ...question, number: firstNumber + order_index, order_index }));
    const nextItems = items.filter((item) => item.id !== selectedItem.id);
    setSelectedId(nextItems[0]?.id ?? "");
    onChange({
      ...group,
      questions,
      config: { items: nextItems },
    });
  }

  function addQuestion() {
    const id = crypto.randomUUID();
    const number = group.questions.length
      ? Math.max(...group.questions.map((question) => question.number)) + 1
      : (baseQuestionNumber ?? 1);
    const question: QuestionModel = {
      id,
      number,
      prompt: "Diagram label {{gap}}",
      config: { max_words: 2, max_numbers: 1 },
      answer_key: { kind: "TEXT", accepted: [], case_sensitive: false },
      order_index: group.questions.length,
    };
    const next = appendDiagramQuestion(group, question);
    setSelectedId((next.config as unknown as DiagramLabellingConfig).items.at(-1)?.id ?? "");
    onChange(next);
  }

  const errors = diagramLabellingErrors(group);
  return (
    <div className="diagram-authoring">
      {errors.length ? <div role="alert" className="notice notice-warning diagram-validation">{errors.map((error) => <p key={error}>{error}</p>)}</div> : null}
      {group.image_asset ? (
        <div className="diagram-canvas-shell">
          <div ref={canvasRef} className={`diagram-canvas ${drag ? "is-dragging" : ""}`}>
            <img src={assetContentUrl(group.image_asset)} alt="Diagram being labelled" />
            <svg className="diagram-arrows" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Diagram callout arrows">
              <defs>
                <marker id={`diagram-arrow-${group.id ?? "draft"}`} markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="userSpaceOnUse">
                  <path d="M0,0 L10,5 L0,10 z" className="diagram-arrow-head" />
                </marker>
              </defs>
              {items.map((item) => (
                <line
                  key={item.id}
                  x1={item.arrow.start_x * 1000}
                  y1={item.arrow.start_y * 1000}
                  x2={item.arrow.end_x * 1000}
                  y2={item.arrow.end_y * 1000}
                  className={item.id === selectedItem?.id ? "diagram-arrow is-selected" : "diagram-arrow"}
                  markerEnd={`url(#diagram-arrow-${group.id ?? "draft"})`}
                  role="button"
                  tabIndex={0}
                  aria-label={`Select arrow for question ${questionFor(group.questions, item)?.number ?? ""}`}
                  onClick={() => setSelectedId(item.id)}
                  onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setSelectedId(item.id); }}
                />
              ))}
            </svg>
            {items.map((item) => {
              const question = questionFor(group.questions, item);
              const [before, after] = splitDiagramPrompt(question?.prompt ?? "");
              return (
                <div
                  key={item.id}
                  data-diagram-item-id={item.id}
                  className={`diagram-label diagram-label-editor ${item.id === selectedItem?.id ? "is-selected" : ""}`}
                  style={{ left: diagramPercent(item.box.x), top: diagramPercent(item.box.y), width: diagramPercent(item.box.width) }}
                  onPointerDown={(event) => beginDrag(event, item, "box")}
                  onPointerMove={moveDrag}
                  onPointerUp={endDrag}
                  onPointerCancel={endDrag}
                  onClick={() => setSelectedId(item.id)}
                >
                  <span className="diagram-drag-grip" aria-hidden="true">⠿</span>
                  <span className="diagram-label-copy"><b>{question?.number ?? "?"}</b> {before}<span className="diagram-gap-placeholder">answer</span>{after}</span>
                </div>
              );
            })}
            {items.map((item) => item.id === selectedItem?.id ? (
              <div key={`${item.id}-handles`} className="diagram-handles">
                <button
                  type="button"
                  className="diagram-arrow-handle diagram-arrow-start"
                  style={{ left: diagramPercent(item.arrow.start_x), top: diagramPercent(item.arrow.start_y) }}
                  aria-label={`Move arrow start for question ${selectedQuestion?.number ?? ""}`}
                  onPointerDown={(event) => beginDrag(event, item, "start")}
                  onPointerMove={moveDrag}
                  onPointerUp={endDrag}
                  onPointerCancel={endDrag}
                />
                <button
                  type="button"
                  className="diagram-arrow-handle diagram-arrow-end"
                  style={{ left: diagramPercent(item.arrow.end_x), top: diagramPercent(item.arrow.end_y) }}
                  aria-label={`Move arrow target for question ${selectedQuestion?.number ?? ""}`}
                  onPointerDown={(event) => beginDrag(event, item, "end")}
                  onPointerMove={moveDrag}
                  onPointerUp={endDrag}
                  onPointerCancel={endDrag}
                />
              </div>
            ) : null)}
          </div>
        </div>
      ) : (
        <div className="diagram-empty-state"><p>Upload a PNG, JPEG, or WEBP diagram to activate the canvas.</p><span>You can still prepare the sentence and answer below.</span></div>
      )}

      <button type="button" className="btn btn-secondary diagram-add-question" onClick={addQuestion}>+ Add question</button>
      {selectedItem && selectedQuestion ? (
        <section className="diagram-inspector" aria-label={`Question ${selectedQuestion.number} diagram inspector`}>
          <div className="diagram-inspector-heading"><div><p className="page-eyebrow">Selected label</p><h3>Question {selectedQuestion.number}</h3></div><button type="button" className="btn btn-danger-ghost" onClick={removeSelected}>Remove question</button></div>
          <label className="field-label">Sentence with one {"{{gap}}"}<textarea aria-label="Diagram sentence" className="field min-h-24 resize-y" value={selectedQuestion.prompt} onChange={(event) => updateQuestion({ prompt: event.target.value })} /></label>
          <div className="diagram-inspector-grid">
            <label className="field-label">Primary accepted answer<input aria-label="Primary accepted answer" className="field" value={acceptedAnswers(selectedQuestion)[0] ?? ""} onChange={(event) => updateQuestion({ answer_key: textKey(selectedQuestion, [event.target.value, ...acceptedAnswers(selectedQuestion).slice(1)]) })} /></label>
            <label className="field-label">Label width (%)<input aria-label="Diagram label width" className="field" type="number" min={DIAGRAM_MIN_WIDTH * 100} max={DIAGRAM_MAX_WIDTH * 100} value={Math.round(selectedItem.box.width * 100)} onChange={(event) => { const width = clamp(Number(event.target.value) / 100, DIAGRAM_MIN_WIDTH, DIAGRAM_MAX_WIDTH); updateItem(selectedItem.id, (item) => ({ ...item, box: { ...item.box, width, x: Math.min(item.box.x, 1 - width) } })); }} /></label>
            <label className="field-label">Maximum words<input aria-label="Diagram maximum words" className="field" type="number" min={1} max={20} value={String(selectedQuestion.config.max_words ?? "")} onChange={(event) => updateQuestion({ config: { ...selectedQuestion.config, max_words: event.target.value ? Number(event.target.value) : null } })} /></label>
            <label className="field-label">Maximum numbers<input aria-label="Diagram maximum numbers" className="field" type="number" min={0} max={20} value={String(selectedQuestion.config.max_numbers ?? "")} onChange={(event) => updateQuestion({ config: { ...selectedQuestion.config, max_numbers: event.target.value === "" ? null : Number(event.target.value) } })} /></label>
          </div>
          <div className="diagram-alternatives"><p className="field-label">Additional accepted answers</p>{acceptedAnswers(selectedQuestion).slice(1).map((answer, index) => <div key={index} className="diagram-alternative-row"><input aria-label={`Diagram alternative answer ${index + 1}`} className="field" value={answer} onChange={(event) => { const accepted = acceptedAnswers(selectedQuestion); accepted[index + 1] = event.target.value; updateQuestion({ answer_key: textKey(selectedQuestion, accepted) }); }} /><button type="button" className="btn btn-danger-ghost" onClick={() => updateQuestion({ answer_key: textKey(selectedQuestion, acceptedAnswers(selectedQuestion).filter((_, answerIndex) => answerIndex !== index + 1)) })}>Remove</button></div>)}<button type="button" className="btn btn-secondary" onClick={() => updateQuestion({ answer_key: textKey(selectedQuestion, [...acceptedAnswers(selectedQuestion), ""]) })}>+ Add alternative answer</button></div>
          <label className="diagram-case-toggle"><input type="checkbox" checked={Boolean(selectedQuestion.answer_key.case_sensitive)} onChange={(event) => updateQuestion({ answer_key: { ...textKey(selectedQuestion, acceptedAnswers(selectedQuestion)), case_sensitive: event.target.checked } })} /> Case-sensitive grading</label>
          <fieldset className="diagram-position-fields"><legend>Precise normalized position</legend>{([[
            "Label X", "box", "x",
          ], ["Label Y", "box", "y"], ["Arrow start X", "arrow", "start_x"], ["Arrow start Y", "arrow", "start_y"], ["Arrow target X", "arrow", "end_x"], ["Arrow target Y", "arrow", "end_y"]] as const).map(([label, section, key]) => <label key={label} className="field-label">{label}<input aria-label={label} className="field" type="number" min={0} max={1} step={0.01} value={positionValue(selectedItem, section, key)} onChange={(event) => { const value = clamp(Number(event.target.value)); updateItem(selectedItem.id, (item) => updatePosition(item, section, key, value)); }} /></label>)}</fieldset>
        </section>
      ) : null}
    </div>
  );
}

export function appendDiagramQuestion(group: QuestionGroupModel, question: QuestionModel): QuestionGroupModel {
  const config = group.config as unknown as DiagramLabellingConfig;
  return {
    ...group,
    questions: [...group.questions, { ...question, order_index: group.questions.length }],
    config: { items: [...(config.items ?? []), createDiagramCanvasItem(question.id!, group.questions.length)] },
  };
}

function questionFor(questions: QuestionModel[], item: DiagramCanvasItem) {
  return questions.find((question) => question.id === item.question_id);
}

function acceptedAnswers(question: QuestionModel): string[] {
  return Array.isArray(question.answer_key.accepted)
    ? (question.answer_key.accepted as unknown[]).map(String)
    : [""];
}

function textKey(question: QuestionModel, accepted: string[]): Record<string, unknown> {
  return { kind: "TEXT", accepted, case_sensitive: Boolean(question.answer_key.case_sensitive) };
}

function clamp(value: number, minimum = 0, maximum = 1): number {
  if (!Number.isFinite(value)) return minimum;
  return Math.min(maximum, Math.max(minimum, value));
}

function positionValue(
  item: DiagramCanvasItem,
  section: "box" | "arrow",
  key: "x" | "y" | "start_x" | "start_y" | "end_x" | "end_y",
): number {
  if (section === "box") return item.box[key as "x" | "y"];
  return item.arrow[key as keyof DiagramCanvasItem["arrow"]];
}

function updatePosition(
  item: DiagramCanvasItem,
  section: "box" | "arrow",
  key: "x" | "y" | "start_x" | "start_y" | "end_x" | "end_y",
  value: number,
): DiagramCanvasItem {
  if (section === "box") {
    const boxKey = key as "x" | "y";
    return {
      ...item,
      box: {
        ...item.box,
        [boxKey]: boxKey === "x" ? Math.min(value, 1 - item.box.width) : value,
      },
    };
  }
  return { ...item, arrow: { ...item.arrow, [key]: value } };
}
