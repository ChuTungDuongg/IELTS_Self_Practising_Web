"use client";

import { SelectableText } from "@/features/highlighting/selectable-text";
import { questionTarget, type RendererProps } from "./renderers";
import type { NoteCompletionLayout } from "./types";

export function NoteCompletionRenderer({ group, values, disabled, onAnswer, highlighting, activeQuestionId }: RendererProps) {
  const layout = group.config.layout as NoteCompletionLayout;
  const title = layout.title?.trim();
  return (
    <section className="note-completion-document">
      {title ? <h3 className="note-completion-title">{title}</h3> : null}
      <div className="note-completion-blocks">
        {layout.blocks.map((block) => (
          <div key={block.id} className={`note-completion-block note-style-${block.style.toLowerCase()} note-indent-${block.indent}`}>
            {block.style === "BULLET" ? <span className="note-completion-marker" aria-hidden="true">•</span> : null}
            <div className="note-completion-line">
              {block.segments.map((segment) => {
                if (segment.type === "TEXT") {
                  return <SelectableText key={segment.id} text={segment.text} target={{ target_kind: "TEXT_COMPLETION_SEGMENT", target_id: group.id, segment_id: segment.id }} controller={highlighting} />;
                }
                const question = group.questions.find((item) => item.id === segment.question_id);
                return question ? (
                  <label key={segment.id} {...questionTarget(question, activeQuestionId, "note-completion-answer")}>
                    <span className="note-completion-question-number">{question.number}</span>
                    <input aria-label={`Question ${question.number}`} className="note-completion-answer-input" disabled={disabled} value={String(values[question.id] ?? "")} onChange={(event) => onAnswer?.(question.id, event.target.value)} />
                  </label>
                ) : null;
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
