"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { elapsedFromSnapshot, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { AttemptStoppedError, useAttemptLifecycle } from "@/features/exam/attempt-lifecycle";
import { countWords } from "@/features/writing/word-count";
import { recordActivity, recordNavigation, saveWritingResponse } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { submitAttempt, type ExamPayload } from "@/lib/api/exam";

type SaveState = "saved" | "saving" | "error";

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
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [clock, setClock] = useState(() => Date.now());
  const contentsRef = useRef(contents);
  const revisions = useRef(new Map(tasks.map((task) => [task.id, 0])));
  const savedRevisions = useRef(new Map(tasks.map((task) => [task.id, 0])));
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const finalized = useRef(false);
  const { stopped, ended, accept, runMutation, isStopped } = useAttemptLifecycle(attemptId, () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
  });
  const offset = useMemo(
    () => estimateServerOffset(initial.attempt.server_time),
    [initial.attempt.server_time],
  );
  const task = tasks[taskIndex];
  useEffect(() => { if (task && !stopped.current) void runMutation(() => recordNavigation(attemptId, "WRITING_TASK", task.id)).catch((error) => { if (!(error instanceof AttemptStoppedError)) setSaveError("Your activity could not be recorded. Please try again."); }); }, [attemptId, runMutation, stopped, task]);

  const persist = useCallback(async (taskId: string, revision: number) => {
    if (isStopped()) throw new AttemptStoppedError();
    const content = contentsRef.current[taskId] ?? "";
    setSaveState("saving");
    setSaveError(null);
    try {
      await runMutation(() => saveWritingResponse(attemptId, taskId, content));
      if (revisions.current.get(taskId) === revision) {
        savedRevisions.current.set(taskId, revision);
        setSaveState("saved");
      }
    } catch (error) {
      if (error instanceof AttemptStoppedError) throw error;
      setSaveState("error");
      setSaveError("Your response could not be saved. Retry before submitting.");
      throw error;
    }
  }, [attemptId, isStopped, runMutation]);

  const saveTask = useCallback(async (taskId: string) => {
    const timer = timers.current.get(taskId);
    if (timer) clearTimeout(timer);
    timers.current.delete(taskId);
    await persist(taskId, revisions.current.get(taskId) ?? 0);
  }, [persist]);

  function updateContent(taskId: string, content: string) {
    if (stopped.current) return;
    const revision = (revisions.current.get(taskId) ?? 0) + 1;
    revisions.current.set(taskId, revision);
    contentsRef.current = { ...contentsRef.current, [taskId]: content };
    setContents(contentsRef.current);
    setSaveState("saving");
    setSaveError(null);
    const timer = timers.current.get(taskId);
    if (timer) clearTimeout(timer);
    timers.current.set(taskId, setTimeout(() => {
      timers.current.delete(taskId);
      void persist(taskId, revision).catch(() => undefined);
    }, 750));
  }

  const flushForSubmission = useCallback(async () => {
    if (isStopped()) throw new AttemptStoppedError();
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    const currentTask = tasks[taskIndex];
    if (currentTask) {
      await persist(currentTask.id, revisions.current.get(currentTask.id) ?? 0);
    }
    for (const candidate of tasks) {
      if (candidate.id === currentTask?.id) continue;
      if ((revisions.current.get(candidate.id) ?? 0) !== (savedRevisions.current.get(candidate.id) ?? 0)) {
        await persist(candidate.id, revisions.current.get(candidate.id) ?? 0);
      }
    }
  }, [isStopped, persist, taskIndex, tasks]);

  const finish = useCallback(async () => {
    if (submitting || isStopped()) return;
    setSubmitting(true);
    let saving = true;
    try {
      await flushForSubmission();
      saving = false;
      await runMutation(() => submitAttempt(attemptId));
      accept({ ...initial.attempt, status: "SUBMITTED" });
    } catch (error) {
      if (!(error instanceof AttemptStoppedError) && !saving) setSaveError("Submission could not be completed. Please try again.");
      setSubmitting(false);
    }
  }, [accept, attemptId, flushForSubmission, initial.attempt, isStopped, runMutation, submitting]);

  useEffect(() => {
    const timerMap = timers.current;
    const ticker = window.setInterval(() => setClock(Date.now()), 1000);
    return () => {
      window.clearInterval(ticker);
      timerMap.forEach(clearTimeout);
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
        void runMutation(() => recordActivity(attemptId)).catch((error) => { if (!(error instanceof AttemptStoppedError)) setSaveError("Your activity could not be recorded. Please try again."); });
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
      <div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flushForSubmission} /><ThemeToggle /><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></div>
    </header>
    <div className="writing-task-tabs" role="tablist" aria-label="Writing tasks">
      {tasks.map((item, index) => <button key={item.id} type="button" role="tab" aria-selected={index === taskIndex} className={index === taskIndex ? "active" : ""} onClick={() => setTaskIndex(index)}><b>Task {item.task_number}</b><span>{countWords(contents[item.id] ?? "")} words</span></button>)}
    </div>
    {saveError ? <div role="alert" className="notice notice-error writing-save-error"><span>{saveError}</span><button type="button" className="btn btn-secondary" onClick={() => void saveTask(task.id).catch(() => undefined)}>Retry save</button></div> : null}
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
        <textarea id={`writing-response-${task.id}`} value={content} onChange={(event) => updateContent(task.id, event.target.value)} spellCheck className="writing-response-textarea" />
        <button type="button" className="btn btn-writing" onClick={() => void saveTask(task.id).catch(() => undefined)}>Save Task {task.task_number}</button>
      </section>
    </main>
    <footer className="exam-footer"><span className="exam-preview-note">Your work is saved automatically.</span><button type="button" onClick={() => void finish()} disabled={submitting} className="exam-submit">{submitting ? "Submitting…" : "Submit Writing"}</button></footer>
  </div>;
}
