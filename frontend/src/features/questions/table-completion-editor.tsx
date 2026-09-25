"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { GapQuestionNavigator } from "./gap-question-navigator";
import type {
  QuestionGroupModel,
  QuestionModel,
  TableCompletionCell,
  TableCompletionLayout,
  TableCompletionSegment,
} from "./types";
import type { EditorProps } from "./editors";

type InsertionPoint = { cellId: string; segmentId?: string; offset?: number };

function emptyCell(): TableCompletionCell {
  return {
    id: crypto.randomUUID(),
    segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "" }],
  };
}

function gapIds(cells: TableCompletionCell[]): Set<string> {
  return new Set(
    cells.flatMap((cell) => cell.segments)
      .filter((segment) => segment.type === "GAP")
      .map((segment) => segment.question_id),
  );
}

function withoutQuestions(group: QuestionGroupModel, removed: Set<string>): QuestionModel[] {
  const firstNumber = Math.min(...group.questions.map((question) => question.number));
  return group.questions
    .filter((question) => !removed.has(question.id ?? ""))
    .map((question, order_index) => ({ ...question, number: firstNumber + order_index, order_index }));
}

function compactSegments(segments: TableCompletionSegment[]): TableCompletionSegment[] {
  const compacted: TableCompletionSegment[] = [];
  for (const segment of segments) {
    const previous = compacted.at(-1);
    if (segment.type === "TEXT" && previous?.type === "TEXT") {
      previous.text += segment.text;
    } else {
      compacted.push({ ...segment });
    }
  }
  return compacted.length ? compacted : [{ id: crypto.randomUUID(), type: "TEXT", text: "" }];
}

function updateQuestion(
  group: QuestionGroupModel,
  questionId: string,
  patch: Partial<QuestionModel>,
): QuestionGroupModel {
  return {
    ...group,
    questions: group.questions.map((question) => question.id === questionId ? { ...question, ...patch } : question),
  };
}

export function TableCompletionEditor({ group, onChange, baseQuestionNumber }: EditorProps) {
  const layout = group.config.layout as TableCompletionLayout;
  const firstCellId = layout.rows[0]?.cells[0]?.id ?? "";
  const firstGapId = layout.rows.flatMap((row) => row.cells)
    .flatMap((cell) => cell.segments)
    .find((segment) => segment.type === "GAP")?.question_id ?? "";
  const [insertionPoint, setInsertionPoint] = useState<InsertionPoint>({ cellId: firstCellId });
  const [selectedQuestionId, setSelectedQuestionId] = useState(firstGapId);
  const [draggingSegmentId, setDraggingSegmentId] = useState("");
  const answerInput = useRef<HTMLInputElement>(null);
  const focusAnswerOnNavigate = useRef(false);

  useLayoutEffect(() => {
    if (!focusAnswerOnNavigate.current) return;
    answerInput.current?.focus();
    focusAnswerOnNavigate.current = false;
  }, [selectedQuestionId]);

  const orderedQuestions = layout.rows.flatMap((row) => row.cells)
    .flatMap((cell) => cell.segments)
    .filter((segment) => segment.type === "GAP")
    .flatMap((gap) => {
      const question = group.questions.find((item) => item.id === gap.question_id);
      return question ? [question] : [];
    });
  const selectedQuestion = group.questions.find((question) => question.id === selectedQuestionId);
  const selectedQuestionIndex = orderedQuestions.findIndex((question) => question.id === selectedQuestionId);

  function commit(nextLayout: TableCompletionLayout, questions = group.questions) {
    onChange({ ...group, config: { ...group.config, layout: nextLayout }, questions });
  }

  function setText(cellId: string, segmentId: string, text: string) {
    commit({
      ...layout,
      rows: layout.rows.map((row) => ({
        ...row,
        cells: row.cells.map((cell) => cell.id !== cellId ? cell : {
          ...cell,
          segments: cell.segments.map((segment) => segment.id === segmentId && segment.type === "TEXT"
            ? { ...segment, text }
            : segment),
        }),
      })),
    });
  }

  function insertGap() {
    const targetCellId = layout.rows.some((row) => row.cells.some((cell) => cell.id === insertionPoint.cellId))
      ? insertionPoint.cellId
      : firstCellId;
    if (!targetCellId) return;
    const questionId = crypto.randomUUID();
    const gap = { id: crypto.randomUUID(), type: "GAP" as const, question_id: questionId };
    const nextLayout: TableCompletionLayout = {
      ...layout,
      rows: layout.rows.map((row) => ({
        ...row,
        cells: row.cells.map((cell) => {
          if (cell.id !== targetCellId) return cell;
          const segmentIndex = cell.segments.findIndex((segment) => (
            segment.id === insertionPoint.segmentId && segment.type === "TEXT"
          ));
          if (segmentIndex < 0) return { ...cell, segments: [...cell.segments, gap] };
          const segment = cell.segments[segmentIndex];
          if (segment.type !== "TEXT") return cell;
          const offset = Math.max(0, Math.min(insertionPoint.offset ?? segment.text.length, segment.text.length));
          return {
            ...cell,
            segments: [
              ...cell.segments.slice(0, segmentIndex),
              { ...segment, text: segment.text.slice(0, offset) },
              gap,
              { id: crypto.randomUUID(), type: "TEXT", text: segment.text.slice(offset) },
              ...cell.segments.slice(segmentIndex + 1),
            ],
          };
        }),
      })),
    };
    const highestNumber = Math.max((baseQuestionNumber ?? 1) - 1, ...group.questions.map((question) => question.number));
    const question: QuestionModel = {
      id: questionId,
      number: highestNumber + 1,
      prompt: "Table gap",
      config: { max_words: 2, max_numbers: 1 },
      answer_key: { kind: "TEXT", accepted: [], case_sensitive: false },
      order_index: group.questions.length,
    };
    setSelectedQuestionId(questionId);
    commit(nextLayout, [...group.questions, question]);
  }

  function removeGap(segmentId: string, questionId: string) {
    const nextLayout: TableCompletionLayout = {
      ...layout,
      rows: layout.rows.map((row) => ({
        ...row,
        cells: row.cells.map((cell) => ({
          ...cell,
          segments: compactSegments(cell.segments.filter((segment) => segment.id !== segmentId)),
        })),
      })),
    };
    if (selectedQuestionId === questionId) setSelectedQuestionId("");
    commit(nextLayout, withoutQuestions(group, new Set([questionId])));
  }

  function moveGap(segmentId: string, targetCellId: string, requestedIndex: number) {
    let sourceCellId = "";
    let sourceIndex = -1;
    let moving: TableCompletionSegment | undefined;
    const rows = layout.rows.map((row) => ({
      ...row,
      cells: row.cells.map((cell) => {
        const index = cell.segments.findIndex((segment) => segment.id === segmentId && segment.type === "GAP");
        if (index < 0) return { ...cell, segments: [...cell.segments] };
        sourceCellId = cell.id;
        sourceIndex = index;
        moving = cell.segments[index];
        return { ...cell, segments: cell.segments.filter((_, itemIndex) => itemIndex !== index) };
      }),
    }));
    if (!moving) return;
    for (const row of rows) {
      const cell = row.cells.find((item) => item.id === targetCellId);
      if (!cell) continue;
      let targetIndex = requestedIndex;
      if (sourceCellId === targetCellId && sourceIndex < requestedIndex) targetIndex -= 1;
      targetIndex = Math.max(0, Math.min(targetIndex, cell.segments.length));
      cell.segments.splice(targetIndex, 0, moving);
    }
    for (const row of rows) {
      for (const cell of row.cells) {
        if (!cell.segments.length) cell.segments.push({ id: crypto.randomUUID(), type: "TEXT", text: "" });
      }
    }
    setDraggingSegmentId("");
    commit({ ...layout, rows });
  }

  function removeRow(rowId: string) {
    const row = layout.rows.find((item) => item.id === rowId);
    if (!row) return;
    const removed = gapIds(row.cells);
    if (removed.has(selectedQuestionId)) setSelectedQuestionId("");
    const rows = layout.rows.filter((item) => item.id !== rowId);
    setInsertionPoint({ cellId: rows[0]?.cells[0]?.id ?? "" });
    commit({ ...layout, rows }, withoutQuestions(group, removed));
  }

  function removeColumn(columnIndex: number) {
    const removed = gapIds(layout.rows.map((row) => row.cells[columnIndex]).filter(Boolean));
    if (removed.has(selectedQuestionId)) setSelectedQuestionId("");
    const columns = layout.columns.filter((_, index) => index !== columnIndex);
    const rows = layout.rows.map((row) => ({
      ...row,
      cells: row.cells.filter((_, index) => index !== columnIndex),
    }));
    setInsertionPoint({ cellId: rows[0]?.cells[0]?.id ?? "" });
    commit({ ...layout, columns, rows }, withoutQuestions(group, removed));
  }

  function updateSelected(patch: Partial<QuestionModel>) {
    if (!selectedQuestion) return;
    onChange(updateQuestion(group, selectedQuestion.id ?? "", patch));
  }

  const accepted = (selectedQuestion?.answer_key.accepted as string[] | undefined) ?? [];

  return (
    <div className="table-completion-authoring space-y-4">
      <section className="matching-section">
        <div className="matching-section-title">
          <div><h3>Table layout</h3><p>Click in a cell to place a gap. Drag a numbered gap between the insertion markers to move it.</p></div>
        </div>
        <label className="field-label table-title-field">
          Table title <span className="font-normal text-[var(--muted)]">(optional)</span>
          <input
            aria-label="Table title"
            className="field"
            maxLength={300}
            value={layout.title ?? ""}
            onChange={(event) => commit({ ...layout, title: event.target.value })}
            onBlur={(event) => commit({ ...layout, title: event.target.value.trim() })}
          />
        </label>
        {layout.title?.trim() ? <p className="table-completion-title table-completion-builder-title">{layout.title.trim()}</p> : null}
        <div className="table-completion-builder-scroll">
          <table className="table-completion-builder-table">
            <thead>
              <tr>
                {layout.columns.map((column, columnIndex) => (
                  <th key={column.id}>
                    <div className="table-completion-column-heading">
                      <input
                        aria-label={`Column ${columnIndex + 1} heading`}
                        className="table-completion-heading-input"
                        value={column.label}
                        onChange={(event) => commit({
                          ...layout,
                          columns: layout.columns.map((item) => item.id === column.id ? { ...item, label: event.target.value } : item),
                        })}
                      />
                      {layout.columns.length > 1 ? (
                        <button type="button" className="icon-button" aria-label={`Remove column ${columnIndex + 1}`} onClick={() => removeColumn(columnIndex)}>×</button>
                      ) : null}
                    </div>
                  </th>
                ))}
                <th className="table-completion-row-action-heading"><span className="sr-only">Row actions</span></th>
              </tr>
            </thead>
            <tbody>
              {layout.rows.map((row, rowIndex) => (
                <tr key={row.id}>
                  {row.cells.map((cell, columnIndex) => (
                    <td
                      key={cell.id}
                      className={insertionPoint.cellId === cell.id ? "is-selected" : ""}
                      onClick={() => setInsertionPoint({ cellId: cell.id })}
                    >
                      <div className="table-completion-cell-editor" aria-label={`Row ${rowIndex + 1} column ${columnIndex + 1} cell`}>
                        {cell.segments.map((segment, segmentIndex) => (
                          <span className="table-completion-segment" key={segment.id}>
                            <span
                              className={`table-gap-drop-target ${draggingSegmentId ? "is-active" : ""}`}
                              role="button"
                              tabIndex={draggingSegmentId ? 0 : -1}
                              aria-label={`Move gap to row ${rowIndex + 1}, column ${columnIndex + 1}, position ${segmentIndex + 1}`}
                              onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; }}
                              onDrop={(event) => {
                                event.preventDefault();
                                const id = draggingSegmentId || event.dataTransfer.getData("text/plain");
                                if (id) moveGap(id, cell.id, segmentIndex);
                              }}
                            />
                            {segment.type === "TEXT" ? (
                              <input
                                aria-label={`Row ${rowIndex + 1} column ${columnIndex + 1} text segment ${segmentIndex + 1}`}
                                className="table-completion-text-segment"
                                style={{ width: `${Math.max(3, Math.min(60, segment.text.length + 1))}ch` }}
                                value={segment.text}
                                placeholder={cell.segments.length === 1 ? "Type cell text" : "Text"}
                                onClick={(event) => event.stopPropagation()}
                                onFocus={(event) => setInsertionPoint({ cellId: cell.id, segmentId: segment.id, offset: event.currentTarget.selectionStart ?? segment.text.length })}
                                onSelect={(event) => setInsertionPoint({ cellId: cell.id, segmentId: segment.id, offset: event.currentTarget.selectionStart ?? segment.text.length })}
                                onChange={(event) => {
                                  setInsertionPoint({ cellId: cell.id, segmentId: segment.id, offset: event.currentTarget.selectionStart ?? event.target.value.length });
                                  setText(cell.id, segment.id, event.target.value);
                                }}
                              />
                            ) : (
                              <button
                                type="button"
                                draggable
                                aria-label={`Table gap question ${group.questions.find((question) => question.id === segment.question_id)?.number ?? "unknown"}`}
                                className={`table-gap-chip ${selectedQuestionId === segment.question_id ? "is-selected" : ""} ${draggingSegmentId === segment.id ? "is-dragged" : ""}`}
                                onClick={(event) => { event.stopPropagation(); setSelectedQuestionId(segment.question_id); setInsertionPoint({ cellId: cell.id }); }}
                                onDragStart={(event) => { setDraggingSegmentId(segment.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", segment.id); }}
                                onDragEnd={() => setDraggingSegmentId("")}
                              >
                                Q{group.questions.find((question) => question.id === segment.question_id)?.number ?? "?"}
                              </button>
                            )}
                          </span>
                        ))}
                        <span
                          className={`table-gap-drop-target ${draggingSegmentId ? "is-active" : ""}`}
                          role="button"
                          tabIndex={draggingSegmentId ? 0 : -1}
                          aria-label={`Move gap to row ${rowIndex + 1}, column ${columnIndex + 1}, position ${cell.segments.length + 1}`}
                          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; }}
                          onDrop={(event) => {
                            event.preventDefault();
                            const id = draggingSegmentId || event.dataTransfer.getData("text/plain");
                            if (id) moveGap(id, cell.id, cell.segments.length);
                          }}
                        />
                      </div>
                    </td>
                  ))}
                  <td className="table-completion-row-action">
                    <button type="button" className="btn btn-danger-ghost" disabled={layout.rows.length === 1} onClick={() => removeRow(row.id)}>Remove row</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-completion-layout-actions">
          <button type="button" className="btn btn-secondary" onClick={() => commit({
            ...layout,
            columns: [...layout.columns, { id: crypto.randomUUID(), label: "Column" }],
            rows: layout.rows.map((row) => ({ ...row, cells: [...row.cells, emptyCell()] })),
          })}>+ Add column</button>
          <button type="button" className="btn btn-secondary" onClick={() => commit({
            ...layout,
            rows: [...layout.rows, { id: crypto.randomUUID(), cells: layout.columns.map(() => emptyCell()) }],
          })}>+ Add row</button>
          <button type="button" className="btn btn-primary" disabled={!firstCellId} onClick={insertGap}>+ Insert gap</button>
        </div>
      </section>

      {selectedQuestion && selectedQuestionIndex >= 0 ? (
        <fieldset className="table-gap-inspector" aria-label={`Question ${selectedQuestion.number} table gap inspector`}>
          <div className="table-gap-inspector-heading">
            <div><span className="page-eyebrow">Selected gap</span><h3>Q{selectedQuestion.number} answer key</h3></div>
            <button
              type="button"
              className="btn btn-danger-ghost"
              onClick={() => {
                const segment = layout.rows.flatMap((row) => row.cells)
                  .flatMap((cell) => cell.segments)
                  .find((item) => item.type === "GAP" && item.question_id === selectedQuestion.id);
                if (segment?.type === "GAP") removeGap(segment.id, segment.question_id);
              }}
            >Remove gap</button>
          </div>
          <GapQuestionNavigator
            questions={orderedQuestions}
            selectedQuestionId={selectedQuestion.id!}
            onSelect={(questionId) => {
              focusAnswerOnNavigate.current = true;
              setSelectedQuestionId(questionId);
            }}
          />
          <div className="table-gap-inspector-grid">
            <label className="field-label sm:col-span-2">Correct answer
              <input
                ref={answerInput}
                aria-label="Correct answer"
                className="field"
                value={accepted[0] ?? ""}
                onChange={(event) => updateSelected({ answer_key: { kind: "TEXT", accepted: [event.target.value, ...accepted.slice(1)], case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })}
              />
            </label>
            <div className="sm:col-span-2">
              <p className="field-label">Alternative answers</p>
              {accepted.slice(1).map((answer, alternativeIndex) => (
                <div key={alternativeIndex} className="mt-2 flex gap-2">
                  <input
                    aria-label={`Alternative answer ${alternativeIndex + 1}`}
                    className="field"
                    value={answer}
                    onChange={(event) => {
                      const next = [...accepted];
                      next[alternativeIndex + 1] = event.target.value;
                      updateSelected({ answer_key: { kind: "TEXT", accepted: next, case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } });
                    }}
                  />
                  <button type="button" className="btn btn-danger-ghost" onClick={() => updateSelected({ answer_key: { kind: "TEXT", accepted: accepted.filter((_, index) => index !== alternativeIndex + 1), case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })}>Remove</button>
                </div>
              ))}
              <button type="button" className="btn btn-secondary mt-2" onClick={() => updateSelected({ answer_key: { kind: "TEXT", accepted: [...accepted, ""], case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })}>+ Add alternative answer</button>
            </div>
            <label className="field-label">Maximum words
              <input type="number" min={1} aria-label="Maximum words" className="field" value={(selectedQuestion.config.max_words as number | undefined) ?? ""} onChange={(event) => updateSelected({ config: { ...selectedQuestion.config, max_words: event.target.value ? Number(event.target.value) : null } })} />
            </label>
            <label className="field-label">Maximum numbers
              <input type="number" min={0} aria-label="Maximum numbers" className="field" value={(selectedQuestion.config.max_numbers as number | undefined) ?? ""} onChange={(event) => updateSelected({ config: { ...selectedQuestion.config, max_numbers: event.target.value ? Number(event.target.value) : null } })} />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={Boolean(selectedQuestion.answer_key.case_sensitive)} onChange={(event) => updateSelected({ answer_key: { kind: "TEXT", accepted, case_sensitive: event.target.checked } })} />
              Case-sensitive grading
            </label>
          </div>
        </fieldset>
      ) : (
        <p className="notice">Insert or select a gap to edit its answer key.</p>
      )}
    </div>
  );
}
