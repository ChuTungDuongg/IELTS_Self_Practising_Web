"use client";

import { assetContentUrl } from "@/lib/api/assets";
import { diagramPercent, splitDiagramPrompt } from "./diagram-labelling";
import { questionTarget, type RendererProps } from "./renderers";
import type { DiagramLabellingConfig } from "./types";

/* eslint-disable @next/next/no-img-element -- the exam diagram keeps its authored aspect ratio */

export function DiagramLabellingRenderer({
  group,
  values,
  disabled,
  onAnswer,
  activeQuestionId,
  presentation,
}: RendererProps) {
  const config = group.config as unknown as DiagramLabellingConfig & { image_asset?: typeof group.image_asset };
  const image = group.image_asset ?? config.image_asset;
  if (!image) return <p className="notice">The diagram image is unavailable.</p>;
  if (presentation === "listening-visual") {
    return (
      <div className="listening-visual-layout">
        <div className="listening-visual-pane">
          <DiagramCanvas group={group} config={config} image={image} activeQuestionId={activeQuestionId} />
        </div>
        <div className="listening-visual-answer-pane space-y-4">
          {group.questions.map((question) => (
            <label key={question.id} {...questionTarget(question, activeQuestionId, "grid gap-2")}>
              <span className="font-medium"><b className="mr-2 text-[var(--accent)]">{question.number}</b>{question.prompt}</span>
              <input
                aria-label={`Question ${question.number}`}
                className="select-field"
                disabled={disabled}
                value={String(values[question.id] ?? "")}
                onChange={(event) => onAnswer?.(question.id, event.target.value)}
              />
            </label>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="diagram-candidate-shell">
      <div className="diagram-canvas diagram-candidate-canvas">
        <img src={assetContentUrl(image)} alt="Diagram to label" />
        <svg className="diagram-arrows" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <marker id={`candidate-diagram-arrow-${group.id}`} markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="userSpaceOnUse">
              <path d="M0,0 L10,5 L0,10 z" className="diagram-arrow-head" />
            </marker>
          </defs>
          {(config.items ?? []).map((item) => (
            <line
              key={item.id}
              x1={item.arrow.start_x * 1000}
              y1={item.arrow.start_y * 1000}
              x2={item.arrow.end_x * 1000}
              y2={item.arrow.end_y * 1000}
              className="diagram-arrow"
              markerEnd={`url(#candidate-diagram-arrow-${group.id})`}
            />
          ))}
        </svg>
        {(config.items ?? []).map((item) => {
          const question = group.questions.find((candidate) => candidate.id === item.question_id);
          if (!question) return null;
          const [before, after] = splitDiagramPrompt(question.prompt);
          return (
            <label
              key={item.id}
              {...questionTarget(question, activeQuestionId, "diagram-label diagram-candidate-label")}
              style={{ left: diagramPercent(item.box.x), top: diagramPercent(item.box.y), width: diagramPercent(item.box.width) }}
            >
              <span className="diagram-label-copy">
                <b className="diagram-question-number">{question.number}</b>{" "}{before}
                <input
                  aria-label={`Question ${question.number}`}
                  className="diagram-gap-input"
                  disabled={disabled}
                  value={String(values[question.id] ?? "")}
                  onChange={(event) => onAnswer?.(question.id, event.target.value)}
                />
                {after}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function DiagramCanvas({
  group,
  config,
  image,
  activeQuestionId,
}: {
  group: RendererProps["group"];
  config: DiagramLabellingConfig;
  image: NonNullable<RendererProps["group"]["image_asset"]>;
  activeQuestionId?: string | null;
}) {
  return (
    <div className="diagram-candidate-shell">
      <div className="diagram-canvas diagram-candidate-canvas">
        <img src={assetContentUrl(image)} alt="Diagram to label" />
        <svg className="diagram-arrows" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <marker id={`candidate-diagram-arrow-static-${group.id}`} markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto" markerUnits="userSpaceOnUse">
              <path d="M0,0 L10,5 L0,10 z" className="diagram-arrow-head" />
            </marker>
          </defs>
          {(config.items ?? []).map((item) => <line key={item.id} x1={item.arrow.start_x * 1000} y1={item.arrow.start_y * 1000} x2={item.arrow.end_x * 1000} y2={item.arrow.end_y * 1000} className="diagram-arrow" markerEnd={`url(#candidate-diagram-arrow-static-${group.id})`} />)}
        </svg>
        {(config.items ?? []).map((item) => {
          const question = group.questions.find((candidate) => candidate.id === item.question_id);
          if (!question) return null;
          return <span key={item.id} className={`diagram-label diagram-candidate-label ${activeQuestionId === question.id ? "exam-question-active" : ""}`} style={{ left: diagramPercent(item.box.x), top: diagramPercent(item.box.y), width: diagramPercent(item.box.width) }}><b className="diagram-question-number">{question.number}</b></span>;
        })}
      </div>
    </div>
  );
}
