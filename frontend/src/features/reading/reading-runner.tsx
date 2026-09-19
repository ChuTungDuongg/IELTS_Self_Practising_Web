"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { formatDuration, elapsedSeconds, estimateServerOffset, remainingSeconds } from "@/features/exam/timer";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { SelectableText, type HighlightController } from "@/features/highlighting/selectable-text";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { recordActivity, saveAnswer } from "@/lib/api/attempts";
import { createHighlight, deleteAllHighlights, deleteHighlight, getExam, saveFlag, submitAttempt, type ExamPassage, type ExamPayload, type HighlightCreate } from "@/lib/api/exam";

export function ReadingRunner({ initial }: { initial: ExamPayload }) {
  const router = useRouter();
  const attemptId = initial.attempt.attempt_id;
  const [passageIndex, setPassageIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.value])))));
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.flagged])))));
  const [highlights, setHighlights] = useState(initial.highlights);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [highlightError, setHighlightError] = useState("");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [clock, setClock] = useState(() => Date.now());
  const dirty = useRef(new Map<string, unknown>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const finalized = useRef(false);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);

  const persist = useCallback(async (questionId: string, value: unknown) => {
    setSaveState("saving");
    try { await saveAnswer(attemptId, questionId, value); dirty.current.delete(questionId); setSaveState("saved"); }
    catch { setSaveState("error"); }
  }, [attemptId]);

  function answer(questionId: string, value: string | string[]) {
    setValues((current) => ({ ...current, [questionId]: value }));
    dirty.current.set(questionId, value);
    const currentTimer = timers.current.get(questionId);
    if (currentTimer) clearTimeout(currentTimer);
    timers.current.set(questionId, setTimeout(() => persist(questionId, value), 400));
  }

  const flush = useCallback(async () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    await Promise.all([...dirty.current].map(([id, value]) => persist(id, value)));
  }, [persist]);

  useEffect(() => {
    const pendingTimers = timers.current;
    const interval = window.setInterval(() => { setClock(Date.now()); void flush(); }, 10_000);
    const clockInterval = window.setInterval(() => setClock(Date.now()), 1000);
    return () => { window.clearInterval(interval); window.clearInterval(clockInterval); pendingTimers.forEach(clearTimeout); };
  }, [flush]);

  useEffect(() => {
    lastActivity.current = Date.now();
    const meaningful = () => {
      const now = Date.now(); lastActivity.current = now;
      if (now - lastHeartbeat.current >= 20_000) { lastHeartbeat.current = now; void recordActivity(attemptId); }
    };
    const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, meaningful, { passive: true }));
    const afk = window.setInterval(() => { if (Date.now() - lastActivity.current >= 300_000) { void getExam(attemptId).finally(() => router.refresh()); } }, 5000);
    return () => { events.forEach((event) => window.removeEventListener(event, meaningful)); window.clearInterval(afk); };
  }, [attemptId, router]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at ? remainingSeconds(initial.attempt.deadline_at, offset, clock) : elapsedSeconds(initial.attempt.started_at, offset, clock);
  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current) {
      finalized.current = true; void flush().finally(() => submitAttempt(attemptId).finally(() => router.push(`/review/${attemptId}`)));
    }
  }, [attemptId, flush, initial.attempt.timer_mode, router, seconds]);

  async function submit() { await flush(); await submitAttempt(attemptId); router.push(`/review/${attemptId}`); }
  const passage = initial.passages[passageIndex];
  if (!passage) return <p>No Reading passage is available.</p>;

  async function toggleFlag(questionId: string) { const next = !flags[questionId]; setFlags((current) => ({ ...current, [questionId]: next })); await saveFlag(attemptId, questionId, next); }
  async function addHighlight(body: HighlightCreate) { const created = await createHighlight(attemptId, body); setHighlights((current) => [...current, created]); }
  async function removeHighlight(id: string) { await deleteHighlight(attemptId, id); setHighlights((current) => current.filter((item) => item.id !== id)); }
  const highlighting: HighlightController = { highlights, onCreate: addHighlight, onDelete: removeHighlight };

  return <div className="exam-runner">
    <header className="exam-header"><div><p>READING</p><h1>{initial.test_title}</h1></div><div className="exam-header-tools"><ThemeToggle /><div className="exam-highlight-toolbar" aria-label="Highlight management"><span>{highlights.length} {highlights.length === 1 ? "highlight" : "highlights"}</span>{highlights.length ? <button type="button" onClick={() => { setHighlightError(""); setConfirmDeleteAll(true); }}>Delete all</button> : null}</div><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></div></header>
    <div className="grid min-h-0 flex-1 lg:grid-cols-2">
      <PassagePane passage={passage} highlighting={highlighting} />
      <div className="exam-questions"><h2>Questions</h2>{passage.question_groups.map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} passageNumber={passage.order_index + 1} /><Renderer group={group as ExamGroup} values={values} passageBlocks={passage.blocks} onAnswer={answer} highlighting={highlighting} /><div className="exam-flags">{group.questions.map((question) => <button key={question.id} onClick={() => toggleFlag(question.id)} className={flags[question.id] ? "flagged" : ""}>{flags[question.id] ? "⚑" : "⚐"} {question.number}</button>)}</div></section>; })}</div>
    </div>
    <footer className="exam-footer"><div>{initial.passages.map((item, index) => <button key={item.id} onClick={() => setPassageIndex(index)} className={index === passageIndex ? "active" : ""}>Passage {item.order_index + 1}</button>)}</div><button onClick={submit} className="exam-submit">Submit answers</button></footer>
    <ConfirmDialog open={confirmDeleteAll} title="Delete all highlights?" description="All highlights in this attempt will be removed. This action cannot be undone." confirmLabel="Delete all highlights" pending={deletingAll} errorMessage={highlightError} onCancel={() => { setConfirmDeleteAll(false); setHighlightError(""); }} onConfirm={() => { setDeletingAll(true); setHighlightError(""); void deleteAllHighlights(attemptId).then(() => { setHighlights([]); setConfirmDeleteAll(false); }).catch(() => setHighlightError("Could not delete the highlights. Please try again.")).finally(() => setDeletingAll(false)); }} />
  </div>;
}

function PassagePane({ passage, highlighting }: { passage: ExamPassage; highlighting: HighlightController }) {
  return <article className="overflow-y-auto p-8"><h2 className="mb-6 text-2xl font-semibold">{passage.title}</h2><div className="space-y-5 leading-8">{passage.blocks.map((block) => { const text = <SelectableText text={block.text} target={{ target_kind: "PASSAGE_BLOCK", target_id: passage.id, segment_id: block.id }} controller={highlighting} />; return block.type === "heading" ? <h3 key={block.id} className="text-lg font-semibold">{text}</h3> : <p key={block.id}><b className="mr-2">{block.label}</b>{text}</p>; })}</div></article>;
}
