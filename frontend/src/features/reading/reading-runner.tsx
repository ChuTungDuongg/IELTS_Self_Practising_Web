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
  const passages = useMemo(() => [...initial.passages].sort((left, right) => left.order_index - right.order_index), [initial.passages]);
  const questions = useMemo(() => passages.flatMap((passage, passageIndex) => [...passage.question_groups]
    .sort((left, right) => left.order_index - right.order_index)
    .flatMap((group) => [...group.questions]
      .sort((left, right) => left.order_index - right.order_index)
      .map((question) => ({ ...question, passageIndex })))), [passages]);
  const [passageIndex, setPassageIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.value])))));
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.flagged])))));
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(() => questions[0]?.id ?? null);
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
  const questionPane = useRef<HTMLDivElement>(null);
  const questionChips = useRef(new Map<string, HTMLButtonElement>());
  const pendingQuestion = useRef<string | null>(null);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);

  const persist = useCallback(async (questionId: string, value: unknown) => {
    setSaveState("saving");
    try { await saveAnswer(attemptId, questionId, value); dirty.current.delete(questionId); setSaveState("saved"); }
    catch { setSaveState("error"); }
  }, [attemptId]);

  function answer(questionId: string, value: string | string[]) {
    setValues((current) => ({ ...current, [questionId]: value }));
    setActiveQuestionId(questionId);
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

  const scrollToQuestion = useCallback((questionId: string) => {
    const target = [...(questionPane.current?.querySelectorAll<HTMLElement>(".exam-question-target[data-question-id]") ?? [])]
      .find((element) => element.dataset.questionId === questionId);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    target.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!pendingQuestion.current) return;
    const questionId = pendingQuestion.current;
    pendingQuestion.current = null;
    scrollToQuestion(questionId);
  }, [passageIndex, scrollToQuestion]);

  useEffect(() => {
    if (!activeQuestionId) return;
    const chip = questionChips.current.get(activeQuestionId);
    if (chip && typeof chip.scrollIntoView === "function") chip.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeQuestionId]);

  useEffect(() => {
    const pane = questionPane.current;
    if (!pane || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
      const questionId = (visible?.target as HTMLElement | undefined)?.dataset.questionId;
      if (questionId) setActiveQuestionId(questionId);
    }, { root: pane, threshold: [0.35, 0.65] });
    pane.querySelectorAll(".exam-question-target[data-question-id]").forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [passageIndex]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at ? remainingSeconds(initial.attempt.deadline_at, offset, clock) : elapsedSeconds(initial.attempt.started_at, offset, clock);
  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current) {
      finalized.current = true; void flush().finally(() => submitAttempt(attemptId).finally(() => router.push(`/review/${attemptId}`)));
    }
  }, [attemptId, flush, initial.attempt.timer_mode, router, seconds]);

  async function submit() { await flush(); await submitAttempt(attemptId); router.push(`/review/${attemptId}`); }
  const passage = passages[passageIndex];
  if (!passage) return <p>No Reading passage is available.</p>;

  async function toggleFlag(questionId: string) { const next = !flags[questionId]; setFlags((current) => ({ ...current, [questionId]: next })); await saveFlag(attemptId, questionId, next); }
  function selectPassage(index: number) {
    setPassageIndex(index);
    setActiveQuestionId(questions.find((question) => question.passageIndex === index)?.id ?? null);
    if (questionPane.current) questionPane.current.scrollTop = 0;
  }
  function navigateToQuestion(questionId: string, ownerPassageIndex: number) {
    setActiveQuestionId(questionId);
    if (ownerPassageIndex !== passageIndex) {
      pendingQuestion.current = questionId;
      setPassageIndex(ownerPassageIndex);
      return;
    }
    scrollToQuestion(questionId);
  }
  async function addHighlight(body: HighlightCreate) { const created = await createHighlight(attemptId, body); setHighlights((current) => [...current, created]); }
  async function removeHighlight(id: string) { await deleteHighlight(attemptId, id); setHighlights((current) => current.filter((item) => item.id !== id)); }
  const highlighting: HighlightController = { highlights, onCreate: addHighlight, onDelete: removeHighlight };

  return <div className="exam-runner">
    <header className="exam-header"><div><p>READING</p><h1>{initial.test_title}</h1></div><div className="exam-header-tools"><ThemeToggle /><div className="exam-highlight-toolbar" aria-label="Highlight management"><span>{highlights.length} {highlights.length === 1 ? "highlight" : "highlights"}</span>{highlights.length ? <button type="button" onClick={() => { setHighlightError(""); setConfirmDeleteAll(true); }}>Delete all</button> : null}</div><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></div></header>
    <div className="grid min-h-0 flex-1 lg:grid-cols-2">
      <PassagePane passage={passage} highlighting={highlighting} />
      <div ref={questionPane} className="exam-questions" onFocusCapture={(event) => { const target = (event.target as HTMLElement).closest<HTMLElement>(".exam-question-target[data-question-id]"); if (target?.dataset.questionId) setActiveQuestionId(target.dataset.questionId); }}><div className="exam-question-panel-heading"><p>Reading · Passage {passage.order_index + 1}</p><h2>Questions</h2></div>{[...passage.question_groups].sort((left, right) => left.order_index - right.order_index).map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} passageNumber={passage.order_index + 1} /><Renderer group={{ ...group, questions: [...group.questions].sort((left, right) => left.order_index - right.order_index) } as ExamGroup} values={values} passageBlocks={passage.blocks} onAnswer={answer} highlighting={highlighting} activeQuestionId={activeQuestionId} /></section>; })}</div>
    </div>
    <footer className="exam-footer reading-exam-footer">
      <div className="exam-footer-navigation">
        <nav className="exam-passage-navigation" aria-label="Passage navigation">{passages.map((item, index) => <button key={item.id} type="button" onClick={() => selectPassage(index)} className={index === passageIndex ? "active" : ""} aria-current={index === passageIndex ? "page" : undefined}>Passage {item.order_index + 1}</button>)}</nav>
        <nav className="exam-question-strip" aria-label="Question navigation">{questions.map((question) => {
          const answered = isAnswered(values[question.id]);
          const flagged = Boolean(flags[question.id]);
          const current = activeQuestionId === question.id;
          return <div key={question.id} data-nav-question-id={question.id} className={`exam-question-chip ${answered ? "answered" : "unanswered"} ${flagged ? "flagged" : ""} ${current ? "current" : ""}`}>
            <button ref={(element) => { if (element) questionChips.current.set(question.id, element); else questionChips.current.delete(question.id); }} type="button" className="exam-question-number" onClick={() => navigateToQuestion(question.id, question.passageIndex)} aria-label={`Go to question ${question.number}`} aria-current={current ? "true" : undefined}>{question.number}</button>
            <button type="button" className="exam-question-flag" onClick={() => void toggleFlag(question.id)} aria-label={`${flagged ? "Unflag" : "Flag"} question ${question.number}`} aria-pressed={flagged}><span aria-hidden="true">{flagged ? "⚑" : "⚐"}</span></button>
          </div>;
        })}</nav>
      </div>
      <button type="button" onClick={submit} className="exam-submit">Submit answers</button>
    </footer>
    <ConfirmDialog open={confirmDeleteAll} title="Delete all highlights?" description="All highlights in this attempt will be removed. This action cannot be undone." confirmLabel="Delete all highlights" pending={deletingAll} errorMessage={highlightError} onCancel={() => { setConfirmDeleteAll(false); setHighlightError(""); }} onConfirm={() => { setDeletingAll(true); setHighlightError(""); void deleteAllHighlights(attemptId).then(() => { setHighlights([]); setConfirmDeleteAll(false); }).catch(() => setHighlightError("Could not delete the highlights. Please try again.")).finally(() => setDeletingAll(false)); }} />
  </div>;
}

function isAnswered(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return value !== null && value !== undefined && value !== "";
}

function PassagePane({ passage, highlighting }: { passage: ExamPassage; highlighting: HighlightController }) {
  return <article className="exam-passage"><div className="exam-passage-content"><p className="exam-passage-kicker">Reading passage {passage.order_index + 1}</p><h2>{passage.title}</h2><div className="exam-passage-body">{passage.blocks.map((block) => { const text = <SelectableText text={block.text} target={{ target_kind: "PASSAGE_BLOCK", target_id: passage.id, segment_id: block.id }} controller={highlighting} />; return block.type === "heading" ? <h3 key={block.id}>{text}</h3> : <p key={block.id} className="exam-passage-paragraph"><b>{block.label}</b>{text}</p>; })}</div></div></article>;
}
