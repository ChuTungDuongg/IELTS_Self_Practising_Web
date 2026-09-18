"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { formatDuration, elapsedSeconds, estimateServerOffset, remainingSeconds } from "@/features/exam/timer";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { snapToWordBoundaries } from "@/features/highlighting/word-boundaries";
import { recordActivity, saveAnswer } from "@/lib/api/attempts";
import { createHighlight, deleteHighlight, getExam, saveFlag, submitAttempt, type ExamPassage, type ExamPayload, type Highlight } from "@/lib/api/exam";

export function ReadingRunner({ initial }: { initial: ExamPayload }) {
  const router = useRouter();
  const attemptId = initial.attempt.attempt_id;
  const [passageIndex, setPassageIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.value])))));
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.flagged])))));
  const [highlights, setHighlights] = useState(initial.highlights);
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

  function answer(questionId: string, value: string) {
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
  async function addHighlight(body: Omit<Highlight, "id" | "created_at">) { const created = await createHighlight(attemptId, body); setHighlights((current) => [...current, created]); }
  async function removeHighlight(id: string) { await deleteHighlight(attemptId, id); setHighlights((current) => current.filter((item) => item.id !== id)); }

  return <div className="-mx-5 -mt-10 flex h-[calc(100vh-4rem)] flex-col bg-[var(--paper)]">
    <header className="flex items-center justify-between border-b border-[var(--line)] bg-[var(--surface)] px-5 py-3"><div><p className="text-xs font-semibold text-[var(--accent)]">READING</p><h1 className="font-semibold">{initial.test_title}</h1></div><div className="flex items-center gap-5"><span className={`font-mono text-lg font-semibold tabular-nums ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "text-red-700" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className="text-xs text-[var(--muted)]">{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></header>
    <div className="grid min-h-0 flex-1 lg:grid-cols-2">
      <PassagePane passage={passage} highlights={highlights.filter((item) => item.passage_id === passage.id)} onCreate={addHighlight} onDelete={removeHighlight} />
      <div className="overflow-y-auto border-l border-[var(--line)] p-6"><h2 className="mb-5 text-xl font-semibold">Questions</h2>{passage.question_groups.map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ExamRenderer; return <section key={group.id} className="mb-8"><p className="mb-4 rounded-md bg-[var(--surface-soft)] p-3 text-sm font-medium">{group.instruction}</p><Renderer group={group as ExamGroup} values={values} passageBlocks={passage.blocks} onAnswer={answer} /><div className="mt-3 flex flex-wrap gap-2">{group.questions.map((question) => <button key={question.id} onClick={() => toggleFlag(question.id)} className={`rounded px-2 py-1 text-xs ${flags[question.id] ? "bg-amber-200 text-amber-900" : "border border-[var(--line)]"}`}>{flags[question.id] ? "⚑" : "⚐"} {question.number}</button>)}</div></section>; })}</div>
    </div>
    <footer className="flex items-center gap-2 border-t border-[var(--line)] bg-[var(--surface)] px-5 py-3"><div className="flex flex-1 gap-2">{initial.passages.map((item, index) => <button key={item.id} onClick={() => setPassageIndex(index)} className={`rounded-md px-3 py-2 text-sm font-semibold ${index === passageIndex ? "bg-[var(--accent)] text-white" : "border border-[var(--line)]"}`}>Passage {index + 1}</button>)}</div><button onClick={submit} className="rounded-md bg-[var(--accent)] px-5 py-2 text-sm font-semibold text-white">Submit</button></footer>
  </div>;
}

function PassagePane({ passage, highlights, onCreate, onDelete }: { passage: ExamPassage; highlights: Highlight[]; onCreate: (body: Omit<Highlight, "id" | "created_at">) => Promise<void>; onDelete: (id: string) => Promise<void> }) {
  function selectText() {
    const selection = window.getSelection(); if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0); const startElement = (range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer as Element)?.closest<HTMLElement>("[data-block-id]"); const endElement = (range.endContainer.nodeType === Node.TEXT_NODE ? range.endContainer.parentElement : range.endContainer as Element)?.closest<HTMLElement>("[data-block-id]");
    if (!startElement || startElement !== endElement) return;
    const beforeStart = range.cloneRange(); beforeStart.selectNodeContents(startElement); beforeStart.setEnd(range.startContainer, range.startOffset);
    const beforeEnd = range.cloneRange(); beforeEnd.selectNodeContents(startElement); beforeEnd.setEnd(range.endContainer, range.endOffset);
    const block = passage.blocks.find((item) => item.id === startElement.dataset.blockId); if (!block) return;
    const [start, end] = snapToWordBoundaries(block.text, beforeStart.toString().length, beforeEnd.toString().length); selection.removeAllRanges();
    void onCreate({ passage_id: passage.id, start_block_id: block.id, start_offset: start, end_block_id: block.id, end_offset: end, selected_text: block.text.slice(start, end) });
  }
  return <article className="overflow-y-auto p-8" onMouseUp={selectText}><h2 className="mb-6 text-2xl font-semibold">{passage.title}</h2><div className="space-y-5 leading-8">{passage.blocks.map((block) => { const blockHighlights = highlights.filter((item) => item.start_block_id === block.id).sort((a, b) => a.start_offset - b.start_offset); const content: React.ReactNode[] = []; let cursor = 0; for (const item of blockHighlights) { if (item.start_offset < cursor) continue; content.push(block.text.slice(cursor, item.start_offset)); content.push(<mark key={item.id} onClick={() => onDelete(item.id)} title="Click to remove highlight" className="cursor-pointer bg-yellow-200 text-slate-950">{block.text.slice(item.start_offset, item.end_offset)}</mark>); cursor = item.end_offset; } content.push(block.text.slice(cursor)); return block.type === "heading" ? <h3 key={block.id} data-block-id={block.id} className="text-lg font-semibold">{content}</h3> : <p key={block.id} data-block-id={block.id}><b className="mr-2">{block.label}</b>{content}</p>; })}</div></article>;
}
