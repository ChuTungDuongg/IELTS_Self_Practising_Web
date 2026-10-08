"use client";

import { useEffect, useState } from "react";
import {
  aiTraits, aiTraitNames, createAIWritingRun, getAIWritingRun, isActiveAIRun,
  listAIWritingRuns, watchAIWritingRun, type AITrait, type AIWritingEvent,
  type AIWritingResult, type AIWritingRun,
} from "@/lib/api/writing-ai";
import { ApiError } from "@/lib/api/client";
import styles from "./writing-ai-assessment.module.css";

type Stage = "analyzing" | "evidence" | "scoring" | "completed";
type TraceState = Partial<Record<AITrait, { stage: Stage; evidence?: AIWritingResult["criteria"]["ta"]["evidence"] }>>;

export function WritingAIAssessment({ attemptId, taskId, hasEssay, canCopy, onCopy }: {
  attemptId: string; taskId: string; hasEssay: boolean; canCopy: boolean;
  onCopy: (result: AIWritingResult) => void;
}) {
  const [runs, setRuns] = useState<AIWritingRun[]>([]);
  const [run, setRun] = useState<AIWritingRun | null>(null);
  const [trace, setTrace] = useState<TraceState>({});
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const active = isActiveAIRun(run);

  useEffect(() => {
    let disposed = false;
    listAIWritingRuns(attemptId, taskId).then((saved) => {
      if (disposed) return;
      setConfigured(saved.configured);
      setRuns(saved.items);
      setRun(saved.items.find((item) => isActiveAIRun(item) || item.status === "COMPLETED") ?? saved.items[0] ?? null);
    }).catch(() => { if (!disposed) setError("Saved AI assessments could not be loaded. You can try grading again."); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [attemptId, taskId]);

  useEffect(() => {
    if (!run || !active) return;
    return watchAIWritingRun(run.id, {
      event(event: AIWritingEvent) {
        const trait = event.payload.criterion;
        if (trait) {
          const stage: Stage = event.event_type === "criterion.completed" ? "completed"
            : event.event_type === "criterion.scoring.started" ? "scoring"
            : event.event_type === "criterion.evidence.completed" ? "evidence" : "analyzing";
          setTrace((current) => ({ ...current, [trait]: { stage, evidence: event.payload.evidence ?? current[trait]?.evidence } }));
          if (event.payload.result) setRun((current) => current ? { ...current, progress: { ...current.progress, [trait]: event.payload.result! } } : current);
        }
        if (event.event_type === "run.failed") setError(event.payload.error_message ?? "AI grading failed. Please regrade.");
      },
      snapshot(saved) {
        setRun(saved);
        setError("");
        setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      },
      error: setError,
    });
  }, [run?.id, active]);

  async function grade(force: boolean) {
    if (starting || active) return;
    setStarting(true); setError(""); setNotice(""); setTrace({});
    try {
      const created = await createAIWritingRun(attemptId, taskId, force);
      const saved = await getAIWritingRun(created.run_id);
      setRun(saved);
      setConfigured(true);
      setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      if (created.cache_hit) setNotice("Restored the saved AI assessment for this response.");
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.message : "AI grading could not start. Please try again.");
      if (failure instanceof ApiError && failure.code === "AI_NOT_CONFIGURED") setConfigured(false);
    } finally { setStarting(false); }
  }

  return <section className={styles.panel} aria-label="AI Assessment">
    <div className={styles.heading}><div><p className="writing-review-kicker">Second opinion</p><h2>AI Assessment · Task 2</h2></div><span className={styles.badge}>Advisory</span></div>
    <p>AI suggestions are a second opinion. Human grading remains authoritative. Only an explicit human Save changes the official Writing score.</p>
    {configured === false ? <p role="status">AI grading is not configured.</p> : null}
    {!hasEssay ? <p>A non-empty saved Task 2 response is required.</p> : null}
    <div className={styles.actions}>
      <button type="button" className="btn btn-writing" disabled={loading || starting || active || !hasEssay || configured === false} onClick={() => void grade(Boolean(run))}>
        {starting ? "Starting AI grading…" : active ? "AI grading in progress…" : run ? "Regrade with AI" : "Grade Task 2 with AI"}
      </button>
      {run?.result && canCopy ? <button type="button" className="btn" disabled={active || starting} onClick={() => { onCopy(run.result!); setNotice("AI suggestions copied. Edit the grading form and use Save Task 2 scores to persist them."); }}>Copy AI suggestions to grading form</button> : null}
    </div>
    {notice ? <p role="status">{notice}</p> : null}
    {error || run?.status === "FAILED" ? <p role="alert" className="notice notice-error">{error || run?.error_message || "AI grading failed. Please regrade."}</p> : null}
    {run ? <details open={active || run.status === "FAILED"} className={styles.trace}>
      <summary>Scoring Trace{active ? " · In progress" : run.status === "FAILED" ? " · Failed" : " · Complete"}</summary>
      <ol aria-live="polite">{aiTraits.map((trait) => {
        const completed = run.progress[trait];
        const step = trace[trait];
        return <li key={trait}>
          <strong>{completed ? `✓ ${aiTraitNames[trait]} — ${completed.score.toFixed(1)}` : step ? `Analyzing ${aiTraitNames[trait]}…` : `${aiTraitNames[trait]} · Waiting`}</strong>
          {step?.stage === "evidence" || step?.stage === "scoring" || completed ? <p>✓ Evidence collected{step?.stage === "scoring" && !completed ? " · Scoring…" : ""}</p> : null}
          {!completed && step?.evidence?.map((item, index) => <blockquote key={index}><q>{item.quote}</q><p>{item.assessment}</p></blockquote>)}
        </li>;
      })}</ol>
    </details> : null}
    {run?.result ? <p className={styles.overall}>AI Task 2 Overall: <strong>{run.result.overall_band.toFixed(1)}</strong><small>Advisory Task 2 score · not the official Writing band</small></p> : null}
    <div className={styles.criteria}>{aiTraits.map((trait) => {
      const assessment = run?.result?.criteria[trait] ?? run?.progress[trait];
      return assessment ? <article key={trait} className={styles.card} aria-label={`AI ${aiTraitNames[trait]}`}>
        <h3>{aiTraitNames[trait]} <strong>{assessment.score.toFixed(1)}</strong></h3><p>{assessment.feedback}</p>
        <h4>Strengths</h4><ul>{assessment.strengths.map((text, index) => <li key={index}>{text}</li>)}</ul>
        <h4>Improvements</h4><ul>{assessment.improvements.map((text, index) => <li key={index}>{text}</li>)}</ul>
        <details><summary>Essay evidence ({assessment.evidence.length})</summary>{assessment.evidence.map((item, index) => <blockquote key={index}><q>{item.quote}</q><p>{item.assessment}</p></blockquote>)}</details>
      </article> : null;
    })}</div>
    {runs.some((item) => item.status === "COMPLETED" && item.id !== run?.id) ? <details className={styles.history}><summary>Previous AI assessments</summary><ul>{runs.filter((item) => item.status === "COMPLETED").map((item) => <li key={item.id}><button type="button" className="btn" disabled={active || starting} onClick={() => { setRun(item); setTrace({}); setError(""); setNotice(""); }}>{new Date(item.created_at).toLocaleString()} · {item.result?.overall_band.toFixed(1)}</button></li>)}</ul></details> : null}
  </section>;
}
