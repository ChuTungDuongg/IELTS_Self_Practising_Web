"use client";

import { useState } from "react";
import Image from "next/image";
import { assetContentUrl } from "@/lib/api/assets";
import { saveWritingScore, type WritingReviewPayload } from "@/lib/api/exam";

const bands = Array.from({ length: 19 }, (_, index) => index / 2);

export function WritingReviewView({ data }: { data: WritingReviewPayload }) {
  const [taskIndex, setTaskIndex] = useState(0);
  const [selectedBand, setSelectedBand] = useState(
    data.review.attempt.band_score === null ? "" : data.review.attempt.band_score.toFixed(1),
  );
  const [savedBand, setSavedBand] = useState(data.review.attempt.band_score);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const task = data.tasks[taskIndex];

  if (!task) return <p>No Writing review content is available.</p>;

  async function saveBand() {
    if (!selectedBand) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await saveWritingScore(
        data.review.attempt.attempt_id,
        Number(selectedBand),
      );
      setSavedBand(response.band_score);
      setMessage("Writing band saved.");
    } catch {
      setError("The Writing band could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="writing-review">
    <header className="review-header">
      <div><p className="page-eyebrow writing-eyebrow">Writing review</p><h1>{data.review.test_title}</h1></div>
      <p className="review-score"><span>Manual result</span><b>{savedBand === null ? "Not graded" : `Band ${savedBand.toFixed(1)}`}</b></p>
    </header>
    <section className="writing-score-panel" aria-label="Manual Writing grade">
      <label className="field-label">Writing band score<select className="select-field mt-2" value={selectedBand} onChange={(event) => setSelectedBand(event.target.value)}><option value="">Not graded</option>{bands.map((band) => <option key={band} value={band.toFixed(1)}>{band.toFixed(1)}</option>)}</select></label>
      <button type="button" className="btn btn-writing" disabled={!selectedBand || saving} onClick={() => void saveBand()}>{saving ? "Saving…" : "Save band score"}</button>
      {message ? <p role="status" className="notice">{message}</p> : null}
      {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
    </section>
    <div className="writing-task-tabs" role="tablist" aria-label="Writing review tasks">
      {data.tasks.map((item, index) => <button key={item.writing_task_id} type="button" role="tab" aria-selected={index === taskIndex} className={index === taskIndex ? "active" : ""} onClick={() => setTaskIndex(index)}><b>Task {item.task_number}</b><span>{item.word_count} words</span></button>)}
    </div>
    <main className="writing-review-layout">
      <article className="writing-task-prompt"><p className="page-eyebrow">Writing Task {task.task_number}</p><h2>Task {task.task_number}</h2><p>{task.prompt}</p>{task.image_asset ? <Image unoptimized width={720} height={420} src={assetContentUrl(task.image_asset)} alt={`Writing Task ${task.task_number} reference`} /> : null}<div className="writing-task-guidance"><span>Minimum {task.minimum_recommended_words ?? "—"} words</span><span>{task.recommended_duration_seconds ? Math.round(task.recommended_duration_seconds / 60) : "—"} minutes suggested</span></div></article>
      <article className="writing-review-response"><div><p className="page-eyebrow">Saved response</p><h2>{task.word_count} words</h2></div><p>{task.content || "No response was saved."}</p></article>
    </main>
  </div>;
}
