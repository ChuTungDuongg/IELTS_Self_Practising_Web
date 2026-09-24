"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { elapsedFromSnapshot, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { AttemptStoppedError, useAttemptLifecycle } from "@/features/exam/attempt-lifecycle";
import { RevisionAutosaveQueue, useRevisionAutosave } from "@/features/exam/revision-autosave";
import { useExamSubmit } from "@/features/exam/use-exam-submit";
import { countWords } from "@/features/writing/word-count";
import { recordActivity, recordNavigation, saveWritingResponse } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { type ExamPayload } from "@/lib/api/exam";

export function WritingRunner({ initial }: { initial: ExamPayload }) {
  const attemptId = initial.attempt.attempt_id;
  const tasks = useMemo(
    () => [...initial.writing_tasks].sort((left, right) => left.order_index - right.order_index),
    [initial.writing_tasks],
  );
  const [taskIndex, setTaskIndex] = useState(0);
  const [contents, setContents] = useState<Record<string, string>>(() =>
    Object.fromEntries(tasks.map((task) => [task.id, task.content])),
  );
  const [activityError, setActivityError] = useState<string | null>(null);
  const [clock, setClock] = useState(() => Date.now());
  const autosaveRef = useRef<RevisionAutosaveQueue<string> | null>(null);
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const finalized = useRef(false);
  const { stopped, ended, accept, runMutation, isStopped } = useAttemptLifecycle(attemptId, () => {
    autosaveRef.current?.stop();
  });
  const sendResponse = useCallback(
    (taskId: string, content: string) => runMutation(() => saveWritingResponse(attemptId, taskId, content)),
    [attemptId, runMutation],
  );
  const { queue: autosave, status: saveState } = useRevisionAutosave<string>(
    sendResponse, 750,
  );
  useEffect(() => { autosaveRef.current = autosave; }, [autosave]);
  const flushForSubmission = useCallback(() => autosave.flush(), [autosave]);
  const { submit: finish, submitting, finalizing, submitError, isFinalizing } = useExamSubmit({
    attemptId, initialAttempt: initial.attempt, flush: flushForSubmission, runMutation, accept, isStopped,
  });
  const offset = useMemo(
    () => estimateServerOffset(initial.attempt.server_time),
    [initial.attempt.server_time],
  );
  const task = tasks[taskIndex];
  useEffect(() => { if (task && !stopped.current) void runMutation(() => recordNavigation(attemptId, "WRITING_TASK", task.id)).catch((error) => { if (!(error instanceof AttemptStoppedError)) setActivityError("Your activity could not be recorded. Please try again."); }); }, [attemptId, runMutation, stopped, task]);

  const saveTask = useCallback(async (taskId: string) => {
    await autosave.saveNow(taskId);
  }, [autosave]);

  function updateContent(taskId: string, content: string) {
    if (stopped.current || isFinalizing()) return;
    setContents((current) => ({ ...current, [taskId]: content }));
    autosave.markDirty(taskId, content);
  }

  useEffect(() => {
    const ticker = window.setInterval(() => setClock(Date.now()), 1000);
    return () => {
      window.clearInterval(ticker);
    };
  }, []);

  useEffect(() => {
    lastActivity.current = Date.now();
    const meaningful = () => {
      if (stopped.current) return;
      const now = Date.now();
      lastActivity.current = now;
      if (now - lastHeartbeat.current >= 20_000) {
        lastHeartbeat.current = now;
        void runMutation(() => recordActivity(attemptId)).catch((error) => { if (!(error instanceof AttemptStoppedError)) setActivityError("Your activity could not be recorded. Please try again."); });
      }
    };
    const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, meaningful, { passive: true }));
    return () => events.forEach((event) => window.removeEventListener(event, meaningful));
  }, [attemptId, runMutation, stopped]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at
    ? remainingSeconds(initial.attempt.deadline_at, offset, clock)
    : elapsedFromSnapshot(initial.attempt.elapsed_seconds, initial.attempt.server_time, offset, clock);

  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current && !stopped.current) {
      finalized.current = true;
      void finish();
    }
  }, [finish, initial.attempt.timer_mode, seconds, stopped]);

  if (ended) return <p role="status">Attempt finished. Opening your result…</p>;
  if (!task) return <p>No Writing tasks are available.</p>;
  const content = contents[task.id] ?? "";

  return <div className="exam-runner writing-exam">
    <header className="exam-header">
      <div><p>WRITING · TASK {task.task_number}</p><h1>{initial.test_title}</h1></div>
      <div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flushForSubmission} /><ThemeToggle /><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : saveState === "dirty" ? "Unsaved" : "Saved"}</span></div></div>
    </header>
    <div className="writing-task-tabs" role="tablist" aria-label="Writing tasks">
      {tasks.map((item, index) => <button key={item.id} type="button" role="tab" aria-selected={index === taskIndex} className={index === taskIndex ? "active" : ""} onClick={() => setTaskIndex(index)}><b>Task {item.task_number}</b><span>{countWords(contents[item.id] ?? "")} words</span></button>)}
    </div>
    {saveState === "error" ? <div role="alert" className="notice notice-error writing-save-error"><span>Your response could not be saved. Retry before submitting.</span><button type="button" className="btn btn-secondary" onClick={() => void flushForSubmission().catch(() => undefined)}>Retry save</button></div> : null}
    {submitError ? <p role="alert" className="notice notice-error">{submitError}</p> : null}
    {activityError ? <p role="alert" className="notice notice-error">{activityError}</p> : null}
    <main className="writing-runner-layout">
      <article className="writing-task-prompt">
        <p className="writing-task-kicker">Writing Task {task.task_number}</p>
        <h2>Task {task.task_number}</h2>
        <p>{task.prompt}</p>
        {task.image_asset ? <Image unoptimized width={720} height={420} src={assetContentUrl(task.image_asset)} alt={`Writing Task ${task.task_number} reference`} /> : null}
        <div className="writing-task-guidance"><span>Write at least {task.minimum_recommended_words ?? "—"} words</span><span>Suggested time: {task.recommended_duration_seconds ? Math.round(task.recommended_duration_seconds / 60) : "—"} minutes</span></div>
      </article>
      <section className="writing-response-pane">
        <div className="writing-response-heading"><div><p>Your response</p><h2>Task {task.task_number}</h2></div><span>{countWords(content)} words</span></div>
        <label className="sr-only" htmlFor={`writing-response-${task.id}`}>Response for Task {task.task_number}</label>
        <textarea id={`writing-response-${task.id}`} value={content} onChange={(event) => updateContent(task.id, event.target.value)} disabled={finalizing} spellCheck className="writing-response-textarea" />
        <button type="button" disabled={finalizing} className="btn btn-writing" onClick={() => void saveTask(task.id).catch(() => undefined)}>Save Task {task.task_number}</button>
      </section>
    </main>
    <footer className="exam-footer"><span className="exam-preview-note">Your work is saved automatically.</span><button type="button" onClick={() => void finish()} disabled={submitting} className="exam-submit">{submitting ? "Submitting…" : "Submit Writing"}</button></footer>
  </div>;
}
