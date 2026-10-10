"use client";

import { useState } from "react";
import { accuracyLabel, focusedUnitLabel } from "@/features/exam/focused-attempt";
import { sectionAudioClip } from "./audio-time";
import { ListeningAudioPlayer } from "./audio-player";
import { questionRegistry } from "@/features/questions/registry";
import { groupQuestionCount, groupQuestionRange } from "@/features/questions/numbering";
import type { ExamGroup } from "@/features/questions/types";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import type { HighlightController } from "@/features/highlighting/selectable-text";
import { assetContentUrl } from "@/lib/api/assets";
import type { getListeningReview } from "@/lib/api/exam";

type ReviewData = Awaited<ReturnType<typeof getListeningReview>>;

export function ListeningReviewView({ data }: { data: ReviewData }) {
  const focused = data.review.attempt.scope === "FOCUSED_UNIT";
  const [partIndex, setPartIndex] = useState(0);
  const part = data.parts[partIndex];
  const answers = new Map(data.review.answers.map((item) => [item.question_id, item]));
  const values = Object.fromEntries(data.review.answers.map((item) => [item.question_id, item.value]));
  const highlighting: HighlightController = { highlights: data.highlights, readOnly: true };

  if (!part) return <p>No Listening review content is available.</p>;
  const playbackClip = focused ? sectionAudioClip(part) : undefined;

  return (
    <div className="listening-review">
      <header className="review-header">
        <div>
          <p className="page-eyebrow listening-eyebrow">{focused ? "Focused practice · Listening" : "Listening review"}</p>
          <h1>{data.review.test_title}</h1>
          {focusedUnitLabel(data.review.attempt) ? <p>{focusedUnitLabel(data.review.attempt)}</p> : null}
        </div>
        <p className="review-score">
          <span>{focused ? "Correct answers" : "Score"}</span>
          <b>{data.review.attempt.raw_score ?? "—"} / {data.review.attempt.max_score ?? "—"}</b>
          <small>{focused ? accuracyLabel(data.review.attempt.raw_score, data.review.attempt.max_score) : data.review.attempt.band_score === null ? "Official band unavailable" : `Band ${data.review.attempt.band_score.toFixed(1)}`}</small>
        </p>
      </header>

      {!focused ? <div className="listening-part-tabs" aria-label="Review sections">
        {data.parts.map((item, index) => (
          <button key={item.id} type="button" className={index === partIndex ? "active" : ""} onClick={() => setPartIndex(index)}>
            <b>Section {item.order_index + 1}</b>
            <span>{item.question_groups.reduce((count, group) => count + groupQuestionCount(group), 0)} questions</span>
          </button>
        ))}
      </div> : null}

      {focused && !playbackClip ? <p role="alert" className="notice">No audio range is configured for this focused section.</p> : data.audio_asset ? <ListeningAudioPlayer src={assetContentUrl(data.audio_asset)} clip={playbackClip} /> : null}

      <section className="review-surface">
        <p className="exam-passage-kicker">Section {part.order_index + 1}</p>
        <h2>{part.title}</h2>
        {part.question_groups.map((group) => {
          const definition = questionRegistry[group.question_type as keyof typeof questionRegistry];
          if (!definition) return null;
          const Renderer = definition.ReviewRenderer;

          return (
            <div key={group.id} className="exam-question-group">
              <QuestionGroupInstruction group={group as ExamGroup} />
              <Renderer group={group as ExamGroup} values={values} disabled highlighting={highlighting} />
              <div className="review-answer-list">
                {group.questions.map((question) => {
                  const answer = answers.get(question.id);
                  const key = question.answer_key;
                  const expected = key.values ?? key.value ?? (key.accepted as string[] | undefined)?.[0] ?? "—";

                  return (
                    <div key={question.id} className={answer?.is_correct ? "review-answer-correct" : "review-answer-wrong"}>
                      <div className="review-answer-heading">
                        <b>{group.question_type === "multiple_choice_multiple" ? groupQuestionRange(group).replace(/^Q/, "Questions ") : `Question ${question.number}`}</b>
                        <span>{answer?.is_correct ? "Correct" : "Needs review"}</span>
                      </div>
                      <div className="review-answer-details">
                        <span><small>Response</small><span>Your answer: {formatValue(answer?.value)}</span></span>
                        <span><small>Answer key</small><span>Correct: {formatValue(expected)}</span></span>
                      </div>
                      {question.explanation ? <p className="review-explanation"><small>Explanation</small>{question.explanation}</p> : null}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </section>
    </div>
  );
}

function formatValue(value: unknown): string {
  return Array.isArray(value) ? value.join(", ") : String(value ?? "—");
}
