"use client";

import { useState } from "react";
import Image from "next/image";
import { assetContentUrl } from "@/lib/api/assets";
import {
  saveWritingTaskScore,
  type WritingReviewPayload,
} from "@/lib/api/exam";

const bands = Array.from({ length: 19 }, (_, index) => (index / 2).toFixed(1));
const criteria = [
  ["ta", "TA", "Task Achievement"],
  ["cc", "CC", "Coherence & Cohesion"],
  ["lr", "LR", "Lexical Resource"],
  ["gra", "GRA", "Grammatical Range & Accuracy"],
] as const;
type Criterion = "ta" | "cc" | "lr" | "gra";
type TaskSelection = Record<Criterion, string>;
type TaskFeedback = Record<Criterion, string>;

function initialSelections(data: WritingReviewPayload): Record<string, TaskSelection> {
  return Object.fromEntries(data.tasks.map((task) => [
    task.writing_task_id,
    {
      ta: task.score?.ta.toFixed(1) ?? "",
      cc: task.score?.cc.toFixed(1) ?? "",
      lr: task.score?.lr.toFixed(1) ?? "",
      gra: task.score?.gra.toFixed(1) ?? "",
    },
  ]));
}

function initialFeedback(data: WritingReviewPayload): Record<string, TaskFeedback> {
  return Object.fromEntries(data.tasks.map((task) => [
    task.writing_task_id,
    {
      ta: task.score?.ta_feedback ?? "",
      cc: task.score?.cc_feedback ?? "",
      lr: task.score?.lr_feedback ?? "",
      gra: task.score?.gra_feedback ?? "",
    },
  ]));
}

export function WritingReviewView({ data }: { data: WritingReviewPayload }) {
  const [reviewData, setReviewData] = useState(data);
  const [taskIndex, setTaskIndex] = useState(0);
  const [selections, setSelections] = useState(() => initialSelections(data));
  const [feedback, setFeedback] = useState(() => initialFeedback(data));
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const task = reviewData.tasks[taskIndex];

  if (!task) return <p>No Writing review content is available.</p>;

  function updateCriterion(taskId: string, criterion: Criterion, value: string) {
    setSelections((current) => ({
      ...current,
      [taskId]: { ...current[taskId], [criterion]: value },
    }));
    setMessages((current) => ({ ...current, [taskId]: "" }));
  }

  function updateFeedback(taskId: string, criterion: Criterion, value: string) {
    setFeedback((current) => ({
      ...current,
      [taskId]: { ...current[taskId], [criterion]: value },
    }));
    setMessages((current) => ({ ...current, [taskId]: "" }));
  }

  async function saveTaskScores(taskId: string, taskNumber: number) {
    const selection = selections[taskId];
    if (!selection || Object.values(selection).some((value) => value === "")) return;
    setSavingTaskId(taskId);
    setErrors((current) => ({ ...current, [taskId]: "" }));
    setMessages((current) => ({ ...current, [taskId]: "" }));
    try {
      const response = await saveWritingTaskScore(
        reviewData.review.attempt.attempt_id,
        taskId,
        {
          ta: Number(selection.ta),
          cc: Number(selection.cc),
          lr: Number(selection.lr),
          gra: Number(selection.gra),
          ta_feedback: feedback[taskId]?.ta.trim() || null,
          cc_feedback: feedback[taskId]?.cc.trim() || null,
          lr_feedback: feedback[taskId]?.lr.trim() || null,
          gra_feedback: feedback[taskId]?.gra.trim() || null,
        },
      );
      setReviewData(response);
      setMessages((current) => ({ ...current, [taskId]: `Task ${taskNumber} scores saved.` }));
    } catch {
      setErrors((current) => ({ ...current, [taskId]: `Task ${taskNumber} scores could not be saved.` }));
    } finally {
      setSavingTaskId(null);
    }
  }

  return <div className="writing-review">
    <header className="review-header">
      <div><p className="writing-review-kicker">Writing review</p><h1>{reviewData.review.test_title}</h1></div>
      <p className="review-score"><span className="review-result-label">Final assessment</span><b>{reviewData.band_score === null ? "Pending" : `Band ${reviewData.band_score.toFixed(1)}`}</b></p>
    </header>

    <section className="writing-assessment-summary" aria-label="Writing assessment summary">
      <div><p className="writing-review-kicker">Final assessment</p><h2>{reviewData.band_score === null ? "Waiting for all 8 criterion scores" : `Band ${reviewData.band_score.toFixed(1)}`}</h2></div>
      <dl>
        <div><dt>Task 1 overall</dt><dd>{formatOverall(reviewData.task1_overall)}</dd></div>
        <div><dt>Task 2 overall</dt><dd>{formatOverall(reviewData.task2_overall)}</dd></div>
        <div><dt>Weighted overall</dt><dd>{formatOverall(reviewData.weighted_overall)}</dd></div>
        <div><dt>Task weighting</dt><dd>Task 1 × 1 · Task 2 × 2</dd></div>
      </dl>
    </section>

    <div className="writing-assessment-grid">
      {reviewData.tasks.map((scoreTask) => {
        const selection = selections[scoreTask.writing_task_id];
        const complete = selection && Object.values(selection).every((value) => value !== "");
        const saving = savingTaskId === scoreTask.writing_task_id;
        return <section key={scoreTask.writing_task_id} className="writing-assessment-card" aria-label={`Task ${scoreTask.task_number} assessment`}>
          <div className="writing-assessment-card-heading"><div><p className="writing-review-kicker">Writing Task {scoreTask.task_number}</p><h2>Task {scoreTask.task_number} assessment</h2></div><strong>{scoreTask.score ? `Overall ${scoreTask.score.overall.toFixed(2)}` : "Awaiting scores"}</strong></div>
          <div className="writing-criteria-grid">
            {criteria.map(([key, abbreviation, fullName]) => <div key={key} className="writing-criterion-field"><label><span><b>{abbreviation}</b><small>{fullName}</small></span><select aria-label={`Task ${scoreTask.task_number} ${abbreviation}`} className="select-field" value={selection?.[key] ?? ""} onChange={(event) => updateCriterion(scoreTask.writing_task_id, key, event.target.value)}><option value="">Not scored</option>{bands.map((band) => <option key={band} value={band}>{band}</option>)}</select></label><label className="field-label">{abbreviation} feedback <span className="font-normal text-[var(--muted)]">(optional)</span><textarea aria-label={`Task ${scoreTask.task_number} ${abbreviation} feedback`} className="textarea-field mt-2" rows={3} maxLength={4000} value={feedback[scoreTask.writing_task_id]?.[key] ?? ""} onChange={(event) => updateFeedback(scoreTask.writing_task_id, key, event.target.value)} /></label></div>)}
          </div>
          <button type="button" className="btn btn-writing" disabled={!complete || saving} onClick={() => void saveTaskScores(scoreTask.writing_task_id, scoreTask.task_number)}>{saving ? "Saving…" : `Save Task ${scoreTask.task_number} scores`}</button>
          {messages[scoreTask.writing_task_id] ? <p role="status" className="notice notice-success">{messages[scoreTask.writing_task_id]}</p> : null}
          {errors[scoreTask.writing_task_id] ? <p role="alert" className="notice notice-error">{errors[scoreTask.writing_task_id]}</p> : null}
        </section>;
      })}
    </div>

    <div className="writing-task-tabs" role="tablist" aria-label="Writing review tasks">
      {reviewData.tasks.map((item, index) => <button key={item.writing_task_id} type="button" role="tab" aria-selected={index === taskIndex} className={index === taskIndex ? "active" : ""} onClick={() => setTaskIndex(index)}><b>Task {item.task_number}</b><span>{item.word_count} words</span></button>)}
    </div>
    <main className="writing-review-layout">
      <article className="writing-task-prompt"><p className="writing-task-kicker">Writing Task {task.task_number}</p><h2>Task {task.task_number}</h2><p>{task.prompt}</p>{task.image_asset ? <Image unoptimized width={720} height={420} src={assetContentUrl(task.image_asset)} alt={`Writing Task ${task.task_number} reference`} /> : null}<div className="writing-task-guidance"><span>Minimum {task.minimum_recommended_words ?? "—"} words</span><span>{task.recommended_duration_seconds ? Math.round(task.recommended_duration_seconds / 60) : "—"} minutes suggested</span></div></article>
      <article className="writing-review-response"><div><p className="writing-response-kicker">Saved response</p><h2>{task.word_count} words</h2></div><p>{task.content || "No response was saved."}</p></article>
    </main>
  </div>;
}

function formatOverall(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}
