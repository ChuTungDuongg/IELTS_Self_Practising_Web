"use client";

import { useState } from "react";
import { ListeningAudioPlayer } from "./audio-player";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { assetContentUrl } from "@/lib/api/assets";
import type { getListeningReview } from "@/lib/api/exam";

type ReviewData = Awaited<ReturnType<typeof getListeningReview>>;

export function ListeningReviewView({ data }: { data: ReviewData }) {
  const [partIndex, setPartIndex] = useState(0); const part = data.parts[partIndex];
  const answers = new Map(data.review.answers.map((item) => [item.question_id, item]));
  const values = Object.fromEntries(data.review.answers.map((item) => [item.question_id, item.value]));
  if (!part) return <p>No Listening review content is available.</p>;
  return <div className="listening-review"><header className="review-header"><div><p className="page-eyebrow listening-eyebrow">Listening review</p><h1>{data.review.test_title}</h1></div><p>Score <b>{data.review.attempt.raw_score ?? "—"} / {data.review.attempt.max_score ?? "—"}</b></p></header>
    <div className="listening-part-tabs">{data.parts.map((item, index) => <button key={item.id} className={index === partIndex ? "active" : ""} onClick={() => setPartIndex(index)}><b>Section {item.order_index + 1}</b><span>{item.question_groups.flatMap((group) => group.questions).length} questions</span></button>)}</div>
    {data.audio_asset ? <ListeningAudioPlayer src={assetContentUrl(data.audio_asset)} /> : null}
    <section className="review-surface"><h2>{part.title}</h2>{part.question_groups.map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ReviewRenderer; return <div key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} /><Renderer group={group as ExamGroup} values={values} disabled /><div className="review-answer-list">{group.questions.map((question) => { const answer = answers.get(question.id); const key = question.answer_key; const expected = key.values ?? key.value ?? (key.accepted as string[] | undefined)?.[0] ?? "—"; return <div key={question.id} className={answer?.is_correct ? "review-answer-correct" : "review-answer-wrong"}><b>Q{question.number}</b><span>Your answer: {formatValue(answer?.value)}</span><span>Correct: {formatValue(expected)}</span>{question.explanation ? <small>{question.explanation}</small> : null}</div>; })}</div></div>; })}</section>
  </div>;
}

function formatValue(value: unknown): string { return Array.isArray(value) ? value.join(", ") : String(value ?? "—"); }
