"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

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
  const { t } = useTranslation();
  const focused = data.review.attempt.scope === "FOCUSED_UNIT";
  const [partIndex, setPartIndex] = useState(0);
  const part = data.parts[partIndex];
  const answers = new Map(data.review.answers.map((item) => [item.question_id, item]));
  const values = Object.fromEntries(data.review.answers.map((item) => [item.question_id, item.value]));
  const highlighting: HighlightController = { highlights: data.highlights, readOnly: true };

  if (!part) return <p>{t("runner.noListeningReview")}</p>;
  const playbackClip = focused ? sectionAudioClip(part) : undefined;

  return (
    <div className="listening-review">
      <header className="review-header">
        <div>
          <p className="page-eyebrow listening-eyebrow">{focused ? t("runner.listeningReviewFocused") : t("runner.listeningReview")}</p>
          <h1>{data.review.test_title}</h1>
          {focusedUnitLabel(data.review.attempt, t) ? <p>{focusedUnitLabel(data.review.attempt, t)}</p> : null}
        </div>
        <p className="review-score">
          <span>{focused ? t("runner.correctAnswers") : t("runner.score")}</span>
          <b>{data.review.attempt.raw_score ?? "—"} / {data.review.attempt.max_score ?? "—"}</b>
          <small>{focused ? accuracyLabel(data.review.attempt.raw_score, data.review.attempt.max_score, t) : data.review.attempt.band_score === null ? t("runner.bandUnavailable") : t("runner.band", { score: data.review.attempt.band_score.toFixed(1) })}</small>
        </p>
      </header>

      {!focused ? <div className="listening-part-tabs" aria-label={t("runner.reviewListening")}>
        {data.parts.map((item, index) => (
          <button key={item.id} type="button" className={index === partIndex ? "active" : ""} onClick={() => setPartIndex(index)}>
            <b>{t("common.sectionNumber", { number: item.order_index + 1 })}</b>
            <span>{t("common.questionsCount", { count: item.question_groups.reduce((count, group) => count + groupQuestionCount(group), 0) })}</span>
          </button>
        ))}
      </div> : null}

      {data.audio_asset ? <>
        <ListeningAudioPlayer src={assetContentUrl(data.audio_asset)} clip={playbackClip} />
        {focused && !playbackClip ? <p className="notice">{t("runner.fullRecordingNotice")}</p> : null}
      </> : focused ? <p className="notice">{t("runner.externalRecordingNotice")}</p> : null}

      <section className="review-surface">
        <p className="exam-passage-kicker">{t("common.sectionNumber", { number: part.order_index + 1 })}</p>
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
                        <b>{group.question_type === "multiple_choice_multiple" ? groupQuestionRange(group).replace(/^Q/, `${t("common.questions")} `) : t("runner.question", { number: question.number })}</b>
                        <span>{answer?.is_correct ? t("runner.correct") : t("runner.needsReview")}</span>
                      </div>
                      <div className="review-answer-details">
                        <span><small>{t("runner.response")}</small><span>{t("runner.yourAnswerValue", { value: formatValue(answer?.value) })}</span></span>
                        <span><small>{t("runner.answerKey")}</small><span>{t("runner.correctValue", { value: formatValue(expected) })}</span></span>
                      </div>
                      {question.explanation ? <p className="review-explanation"><small>{t("runner.explanation")}</small>{question.explanation}</p> : null}
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
