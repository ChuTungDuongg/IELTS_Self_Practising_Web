"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { formatDuration, elapsedSeconds, estimateServerOffset, remainingSeconds } from "@/features/exam/timer";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { recordActivity, saveAnswer } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { getExam, saveFlag, submitAttempt, type ExamPayload } from "@/lib/api/exam";
import { ListeningAudioPlayer } from "./audio-player";

export function ListeningRunner({ initial }: { initial: ExamPayload }) {
  const router = useRouter(); const attemptId = initial.attempt.attempt_id;
  const [partIndex, setPartIndex] = useState(0);
  const allQuestions = initial.listening_parts.flatMap((part) => part.question_groups.flatMap((group) => group.questions));
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(allQuestions.map((question) => [question.id, question.value])));
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(allQuestions.map((question) => [question.id, question.flagged])));
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [clock, setClock] = useState(() => Date.now());
  const dirty = useRef(new Map<string, unknown>()); const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>()); const finalized = useRef(false); const lastActivity = useRef(0); const lastHeartbeat = useRef(0);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);
  const persist = useCallback(async (id: string, value: unknown) => { setSaveState("saving"); try { await saveAnswer(attemptId, id, value); dirty.current.delete(id); setSaveState("saved"); } catch { setSaveState("error"); } }, [attemptId]);
  function answer(id: string, value: string | string[]) { setValues((current) => ({ ...current, [id]: value })); dirty.current.set(id, value); const timer = timers.current.get(id); if (timer) clearTimeout(timer); timers.current.set(id, setTimeout(() => persist(id, value), 400)); }
  const flush = useCallback(async () => { timers.current.forEach(clearTimeout); timers.current.clear(); await Promise.all([...dirty.current].map(([id, value]) => persist(id, value))); }, [persist]);
  useEffect(() => { const timerMap = timers.current; const interval = window.setInterval(() => void flush(), 10_000); const ticker = window.setInterval(() => setClock(Date.now()), 1000); return () => { clearInterval(interval); clearInterval(ticker); timerMap.forEach(clearTimeout); }; }, [flush]);
  useEffect(() => { const meaningful = () => { const now = Date.now(); lastActivity.current = now; if (now - lastHeartbeat.current > 20_000) { lastHeartbeat.current = now; void recordActivity(attemptId); } }; const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"]; events.forEach((event) => window.addEventListener(event, meaningful, { passive: true })); const afk = window.setInterval(() => { if (Date.now() - lastActivity.current > 300_000) void getExam(attemptId).finally(() => router.refresh()); }, 5000); return () => { events.forEach((event) => window.removeEventListener(event, meaningful)); clearInterval(afk); }; }, [attemptId, router]);
  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at ? remainingSeconds(initial.attempt.deadline_at, offset, clock) : elapsedSeconds(initial.attempt.started_at, offset, clock);
  useEffect(() => { if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current) { finalized.current = true; void flush().finally(() => submitAttempt(attemptId).finally(() => router.push(`/review/${attemptId}`))); } }, [attemptId, flush, initial.attempt.timer_mode, router, seconds]);
  const part = initial.listening_parts[partIndex]; if (!part) return <p>No Listening part is available.</p>;
  async function toggleFlag(id: string) { const next = !flags[id]; setFlags((current) => ({ ...current, [id]: next })); await saveFlag(attemptId, id, next); }
  async function submit() { await flush(); await submitAttempt(attemptId); router.push(`/review/${attemptId}`); }

  return <div className="exam-runner listening-exam"><header className="exam-header"><div><p>LISTENING · PART {partIndex + 1}</p><h1>{initial.test_title}</h1></div><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></header>
    {part.audio_asset ? <ListeningAudioPlayer key={part.id} src={assetContentUrl(part.audio_asset)} /> : <p className="notice notice-error m-4">This part has no audio recording.</p>}
    <main className="listening-question-pane"><div className="listening-question-heading"><div><p>Listening · Part {partIndex + 1}</p><h2>{part.title}</h2></div><span>{part.question_groups.flatMap((group) => group.questions).length} questions</span></div>{part.question_groups.map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><p className="exam-instruction">{group.instruction}</p><Renderer group={group as ExamGroup} values={values} onAnswer={answer} /><div className="exam-flags">{group.questions.map((question) => <button key={question.id} onClick={() => void toggleFlag(question.id)} className={flags[question.id] ? "flagged" : ""}>{flags[question.id] ? "⚑" : "⚐"} {question.number}</button>)}</div></section>; })}</main>
    <footer className="exam-footer"><div>{initial.listening_parts.map((item, index) => <button key={item.id} onClick={() => setPartIndex(index)} className={index === partIndex ? "active" : ""}>Part {index + 1}</button>)}</div><button onClick={() => void submit()} className="exam-submit">Submit answers</button></footer>
  </div>;
}
