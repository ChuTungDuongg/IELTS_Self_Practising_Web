"use client";

import { Fragment } from "react";
import type { TableCompletionLayout } from "./types";
import { questionTarget, type RendererProps } from "./renderers";

export function TableCompletionRenderer({ group, values, disabled, onAnswer, activeQuestionId }: RendererProps) {
  const layout = group.config.layout as TableCompletionLayout;
  const title = layout.title?.trim();

  return (
    <figure className="table-completion-figure">
      {title ? <figcaption className="table-completion-title">{title}</figcaption> : null}
      <div className="table-completion-candidate-scroll">
        <table className="table-completion-candidate-table">
          <thead>
            <tr>{layout.columns.map((column) => <th key={column.id}>{column.label}</th>)}</tr>
          </thead>
          <tbody>
            {layout.rows.map((row) => (
              <tr key={row.id}>
                {row.cells.map((cell) => (
                  <td key={cell.id}>
                    {cell.segments.map((segment) => {
                      if (segment.type === "TEXT") return <Fragment key={segment.id}>{segment.text}</Fragment>;
                      const question = group.questions.find((item) => item.id === segment.question_id);
                      return question ? (
                        <label key={segment.id} {...questionTarget(question, activeQuestionId, "table-completion-answer")}>
                          <span className="table-completion-question-number">{question.number}</span>
                          <input
                            aria-label={`Question ${question.number}`}
                            className="table-completion-answer-input"
                            disabled={disabled}
                            value={String(values[question.id] ?? "")}
                            onChange={(event) => onAnswer?.(question.id, event.target.value)}
                          />
                        </label>
                      ) : null;
                    })}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
