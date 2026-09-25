"use client";

import { useState } from "react";
import { SelectableText, type HighlightController } from "@/features/highlighting/selectable-text";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import { groupQuestionCount, groupQuestionRange } from "@/features/questions/numbering";
import type { ExamGroup } from "@/features/questions/types";

type ReviewData = Awaited<ReturnType<typeof import("@/lib/api/exam").getReadingReview>>;

export function ReadingReviewView({ data }: { data: ReviewData }) {
  const [passageIndex, setPassageIndex] = useState(0);
  const passage = data.passages[passageIndex];
  const answers = new Map(data.review.answers.map((item) => [item.question_id, item]));
  const values = Object.fromEntries(data.review.answers.map((item) => [item.question_id, item.value]));
  const highlighting: HighlightController = { highlights: data.highlights, readOnly: true };

  if (!passage) return <p>No Reading review content is available.</p>;

  const highlightBlock = (block: { id: string; text: string }) => (
    <SelectableText
      text={block.text}
      target={{ target_kind: "PASSAGE_BLOCK", target_id: passage.id, segment_id: block.id }}
      controller={highlighting}
    />
  );

  return (
    <div className="reading-review">
      <header className="review-header">
        <div>
          <p className="page-eyebrow reading-eyebrow">Reading review</p>
          <h1>{data.review.test_title}</h1>
        </div>
        <p className="review-score">
          <span>Score</span>
          <b>{data.review.attempt.raw_score ?? "—"} / {data.review.attempt.max_score ?? "—"}</b>
          <small>{data.review.attempt.band_score === null ? "Official band unavailable" : `Band ${data.review.attempt.band_score.toFixed(1)}`}</small>
        </p>
      </header>

      <div className="listening-part-tabs" aria-label="Review passages">
        {data.passages.map((item, index) => (
          <button key={item.id} type="button" className={index === passageIndex ? "active" : ""} onClick={() => setPassageIndex(index)}>
            <b>Passage {item.order_index + 1}</b>
            <span>{item.question_groups.reduce((count, group) => count + groupQuestionCount(group), 0)} questions</span>
          </button>
        ))}
      </div>

      <section key={passage.id} className="review-layout">
        <article className="review-passage">
          <p className="exam-passage-kicker">Passage {passage.order_index + 1}</p>
          <h2>{passage.title}</h2>
          <div className="review-passage-body">
            {passage.blocks.map((block) => block.type === "heading" ? (
              <h3 key={block.id}>{highlightBlock(block)}</h3>
            ) : (
              <p key={block.id}><b>{block.label}</b>{highlightBlock(block)}</p>
            ))}
          </div>
        </article>

        <div className="review-questions">
          {passage.question_groups.map((group) => {
            const definition = questionRegistry[group.question_type as keyof typeof questionRegistry];
            if (!definition) return null;
            const Renderer = definition.ReviewRenderer;

            return (
              <div key={group.id} className="review-question-group">
                <QuestionGroupInstruction group={group as ExamGroup} passageNumber={passage.order_index + 1} />
                <Renderer group={group as ExamGroup} values={values} passageBlocks={passage.blocks} disabled highlighting={highlighting} />
                <div className="review-answer-list">
                  {group.questions.map((question) => {
                    const answer = answers.get(question.id);
                    const optionLists = [
                      ...((group.config.options as Array<{ id: string; label: string; text: string }> | undefined) ?? []),
                      ...((question.config.options as Array<{ id: string; label: string; text: string }> | undefined) ?? []),
                    ];
                    const display = (value: unknown) => {
                      const option = optionLists.find((item) => item.id === value);
                      return option ? `${option.label} — ${option.text}` : String(value ?? "—");
                    };
                    const expected = question.answer_key.value ?? (question.answer_key.accepted as string[] | undefined)?.[0];

                    return (
                      <div key={question.id} className={answer?.is_correct ? "review-answer-correct" : "review-answer-wrong"}>
                        <div className="review-answer-heading">
                          <b>{group.question_type === "multiple_choice_multiple" ? groupQuestionRange(group).replace(/^Q/, "Questions ") : `Question ${question.number}`}</b>
                          <span>{answer?.is_correct ? "Correct" : "Needs review"}</span>
                        </div>
                        <div className="review-answer-details">
                          <span><small>Your answer</small>{display(answer?.value)}</span>
                          <span><small>Correct answer</small>{display(expected)}</span>
                        </div>
                        {question.explanation ? <p className="review-explanation"><small>Explanation</small>{question.explanation}</p> : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
