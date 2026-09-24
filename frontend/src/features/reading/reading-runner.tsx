"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { elapsedFromSnapshot, formatDuration, estimateServerOffset, remainingSeconds } from "@/features/exam/timer";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { AttemptStoppedError, useAttemptLifecycle } from "@/features/exam/attempt-lifecycle";
import { RevisionAutosaveQueue } from "@/features/exam/revision-autosave";
import { useExamDraftAutosave } from "@/features/exam/use-exam-draft-autosave";
import { DraftRecoveryNotices } from "@/features/exam/draft-recovery-notices";
import { useExamSubmit } from "@/features/exam/use-exam-submit";
import { revealQuestionChip, scrollQuestionIntoPane } from "@/features/exam/question-navigation";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { SelectableText, type HighlightController } from "@/features/highlighting/selectable-text";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { recordActivity, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { createHighlight, deleteAllHighlights, deleteHighlight, getExam, saveFlag, type ExamPassage, type ExamPayload, type HighlightCreate } from "@/lib/api/exam";

export function ReadingRunner({ initial }: { initial: ExamPayload }) {
  const attemptId = initial.attempt.attempt_id;
  const passages = useMemo(() => [...initial.passages].sort((left, right) => left.order_index - right.order_index), [initial.passages]);
  const questions = useMemo(() => passages.flatMap((passage, passageIndex) => [...passage.question_groups]
    .sort((left, right) => left.order_index - right.order_index)
    .flatMap((group) => [...group.questions]
      .sort((left, right) => left.order_index - right.order_index)
      .map((question) => ({ ...question, passageIndex })))), [passages]);
  const [passageIndex, setPassageIndex] = useState(0);
  const initialResponses = useMemo(() => questions.map((question) => ({ id: question.id, value: question.value, revision: question.answer_revision })), [questions]);
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(initial.passages.flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => [question.id, question.flagged])))));
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(() => questions[0]?.id ?? null);
  const [highlights, setHighlights] = useState(initial.highlights);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [highlightError, setHighlightError] = useState("");
  const [actionError, setActionError] = useState("");
  const [clock, setClock] = useState(() => Date.now());
  const autosaveRef = useRef<RevisionAutosaveQueue<unknown> | null>(null);
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const finalized = useRef(false);
  const questionPane = useRef<HTMLDivElement>(null);
  const questionStrip = useRef<HTMLElement>(null);
  const questionChips = useRef(new Map<string, HTMLButtonElement>());
  const pendingQuestion = useRef<string | null>(null);
  const programmaticNavigation = useRef<string | null>(null);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);
  const { stopped, ended, accept, runMutation, isStopped } = useAttemptLifecycle(attemptId, () => {
    autosaveRef.current?.stop();
  });
  const sendAnswer = useCallback(
    (questionId: string, value: unknown, revision: number) => runMutation(() => saveAnswer(attemptId, questionId, value, revision)),
    [attemptId, runMutation],
  );
  const { queue: autosave, status: saveState, offline, values, conflicts, edit, resolveConflict, flush } = useExamDraftAutosave<unknown>({
    attempt: initial.attempt, initialResponses, save: sendAnswer, debounceMs: 400,
  });
  useEffect(() => { autosaveRef.current = autosave; }, [autosave]);
  const { submit, submitting, finalizing, submitError, isFinalizing } = useExamSubmit({
    attemptId, initialAttempt: initial.attempt, flush, runMutation, accept, isStopped,
  });

  function answer(questionId: string, value: string | string[]) {
    if (stopped.current || isFinalizing()) return;
    programmaticNavigation.current = null;
    if (!edit(questionId, value)) return;
    setActiveQuestionId(questionId);
  }

  useEffect(() => {
    const interval = window.setInterval(() => { if (!stopped.current) void flush().catch(() => undefined); }, 10_000);
    const clockInterval = window.setInterval(() => setClock(Date.now()), 1000);
    return () => { window.clearInterval(interval); window.clearInterval(clockInterval); };
  }, [flush, stopped]);

  useEffect(() => {
    lastActivity.current = Date.now();
    const meaningful = () => {
      if (stopped.current) return;
      const now = Date.now(); lastActivity.current = now;
      if (now - lastHeartbeat.current >= 20_000) { lastHeartbeat.current = now; void runMutation(() => recordActivity(attemptId)).catch(() => undefined); }
    };
    const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, meaningful, { passive: true }));
    const afk = window.setInterval(() => { if (!stopped.current && Date.now() - lastActivity.current >= 300_000) { void getExam(attemptId).then((exam) => accept(exam.attempt)).catch(() => undefined); } }, 5000);
    return () => { events.forEach((event) => window.removeEventListener(event, meaningful)); window.clearInterval(afk); };
  }, [accept, attemptId, runMutation, stopped]);

  const holdNavigation = useCallback((questionId: string | null) => {
    // Observer entries queued by a jump can arrive after the pane has settled.
    // Manual pane interaction releases this guard before visibility tracking resumes.
    programmaticNavigation.current = questionId;
  }, []);

  const scrollToQuestion = useCallback((questionId: string): boolean => {
    const pane = questionPane.current;
    const target = [...(pane?.querySelectorAll<HTMLElement>(".exam-question-target[data-question-id]") ?? [])]
      .find((element) => element.dataset.questionId === questionId);
    if (!pane || !target) return false;
    scrollQuestionIntoPane(pane, target);
    return true;
  }, []);

  useEffect(() => {
    const pane = questionPane.current;
    if (!pane || !pendingQuestion.current) return;
    const complete = () => {
      const questionId = pendingQuestion.current;
      if (questionId && scrollToQuestion(questionId)) {
        pendingQuestion.current = null;
        holdNavigation(questionId);
        observer.disconnect();
      }
    };
    const observer = new MutationObserver(complete);
    complete();
    if (!pendingQuestion.current) return;
    observer.observe(pane, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [activeQuestionId, holdNavigation, passageIndex, scrollToQuestion]);

  useEffect(() => {
    if (!activeQuestionId || !questionStrip.current) return;
    const chip = questionChips.current.get(activeQuestionId);
    if (chip) revealQuestionChip(questionStrip.current, chip);
  }, [activeQuestionId]);

  useEffect(() => {
    const pane = questionPane.current;
    if (!pane || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (programmaticNavigation.current || pendingQuestion.current) return;
      const visible = entries.filter((entry) => entry.isIntersecting).sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
      const questionId = (visible?.target as HTMLElement | undefined)?.dataset.questionId;
      if (questionId && pane.contains(visible.target)) setActiveQuestionId(questionId);
    }, { root: pane, threshold: [0.35, 0.65] });
    pane.querySelectorAll(".exam-question-target[data-question-id]").forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [passageIndex]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at ? remainingSeconds(initial.attempt.deadline_at, offset, clock) : elapsedFromSnapshot(initial.attempt.elapsed_seconds, initial.attempt.server_time, offset, clock);
  useEffect(() => { const passage = passages[passageIndex]; if (passage && !stopped.current) void runMutation(() => recordNavigation(attemptId, "PASSAGE", passage.id)).catch(() => undefined); }, [attemptId, passageIndex, passages, runMutation, stopped]);
  useEffect(() => { if (activeQuestionId && !stopped.current) void runMutation(() => recordNavigation(attemptId, "QUESTION", activeQuestionId)).catch(() => undefined); }, [activeQuestionId, attemptId, runMutation, stopped]);
  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current && !stopped.current) {
      finalized.current = true; void submit();
    }
  });

  const passage = passages[passageIndex];
  if (ended) return <p role="status">Attempt finished. Opening your result…</p>;
  if (!passage) return <p>No Reading passage is available.</p>;

  async function toggleFlag(questionId: string) { if (stopped.current) return; const next = !flags[questionId]; setFlags((current) => ({ ...current, [questionId]: next })); try { await runMutation(() => saveFlag(attemptId, questionId, next)); } catch (error) { if (!(error instanceof AttemptStoppedError)) setActionError("Could not save the flag. Please try again."); } }
  function selectPassage(index: number) {
    pendingQuestion.current = null;
    const firstQuestionId = questions.find((question) => question.passageIndex === index)?.id ?? null;
    holdNavigation(firstQuestionId);
    setPassageIndex(index);
    setActiveQuestionId(firstQuestionId);
    if (questionPane.current) questionPane.current.scrollTop = 0;
  }
  function navigateToQuestion(questionId: string, ownerPassageIndex: number) {
    holdNavigation(questionId);
    setActiveQuestionId(questionId);
    if (ownerPassageIndex !== passageIndex) {
      pendingQuestion.current = questionId;
      setPassageIndex(ownerPassageIndex);
      return;
    }
    if (!scrollToQuestion(questionId)) pendingQuestion.current = questionId;
  }
  async function addHighlight(body: HighlightCreate) { if (stopped.current) return; try { const created = await runMutation(() => createHighlight(attemptId, body)); setHighlights((current) => [...current, created]); } catch (error) { if (!(error instanceof AttemptStoppedError)) setHighlightError("Could not save the highlight. Please try again."); } }
  async function removeHighlight(id: string) { if (stopped.current) return; try { await runMutation(() => deleteHighlight(attemptId, id)); setHighlights((current) => current.filter((item) => item.id !== id)); } catch (error) { if (!(error instanceof AttemptStoppedError)) setHighlightError("Could not delete the highlight. Please try again."); } }
  const highlighting: HighlightController = { highlights, onCreate: addHighlight, onDelete: removeHighlight };

  return <div className="exam-runner">
    <header className="exam-header"><div><p>READING</p><h1>{initial.test_title}</h1></div><div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flush} /><ThemeToggle /><div className="exam-highlight-toolbar" aria-label="Highlight management"><span>{highlights.length} {highlights.length === 1 ? "highlight" : "highlights"}</span>{highlights.length ? <button type="button" onClick={() => { setHighlightError(""); setConfirmDeleteAll(true); }}>Delete all</button> : null}</div><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{initial.attempt.timer_mode === "COUNT_UP" ? "Time used " : ""}{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "conflict" ? "This response changed in another tab or session." : saveState === "error" ? "Save failed" : saveState === "dirty" ? "Unsaved" : "Saved"}</span>{saveState === "error" ? <button type="button" onClick={() => void flush().catch(() => undefined)}>Retry save</button> : null}{saveState === "conflict" ? <button type="button" onClick={() => window.location.reload()}>Reload latest</button> : null}</div></div></header>
    {submitError ? <p role="alert" className="notice notice-error">{submitError}</p> : null}
    <DraftRecoveryNotices offline={offline} conflicts={conflicts} labelFor={(id) => `question ${questions.find((question) => question.id === id)?.number ?? id}`} onResolve={resolveConflict} />
    {actionError ? <p role="alert" className="notice notice-error">{actionError}</p> : null}
    {highlightError && !confirmDeleteAll ? <p role="alert" className="notice notice-error">{highlightError}</p> : null}
    <div className="grid min-h-0 flex-1 lg:grid-cols-2">
      <PassagePane passage={passage} highlighting={highlighting} />
      <div ref={questionPane} inert={finalizing} className="exam-questions" onWheelCapture={() => { programmaticNavigation.current = null; }} onTouchStartCapture={() => { programmaticNavigation.current = null; }} onPointerDownCapture={() => { programmaticNavigation.current = null; }} onKeyDownCapture={() => { programmaticNavigation.current = null; }} onFocusCapture={(event) => { const target = (event.target as HTMLElement).closest<HTMLElement>(".exam-question-target[data-question-id]"); if (target?.dataset.questionId) { programmaticNavigation.current = null; setActiveQuestionId(target.dataset.questionId); } }}><div className="exam-question-panel-heading"><p>Reading · Passage {passage.order_index + 1}</p><h2>Questions</h2></div>{[...passage.question_groups].sort((left, right) => left.order_index - right.order_index).map((group) => { const definition = questionRegistry[group.question_type as keyof typeof questionRegistry]; if (!definition) return null; const Renderer = definition.ExamRenderer; return <section key={group.id} className="exam-question-group"><QuestionGroupInstruction group={group as ExamGroup} passageNumber={passage.order_index + 1} /><Renderer group={{ ...group, questions: [...group.questions].sort((left, right) => left.order_index - right.order_index) } as ExamGroup} values={values} passageBlocks={passage.blocks} onAnswer={answer} highlighting={highlighting} activeQuestionId={activeQuestionId} /></section>; })}</div>
    </div>
    <footer className="exam-footer reading-exam-footer">
      <div className="exam-footer-navigation">
        <nav className="exam-passage-navigation" aria-label="Passage navigation">{passages.map((item, index) => <button key={item.id} type="button" onClick={() => selectPassage(index)} className={index === passageIndex ? "active" : ""} aria-current={index === passageIndex ? "page" : undefined}>Passage {item.order_index + 1}</button>)}</nav>
        <nav ref={questionStrip} className="exam-question-strip" aria-label="Question navigation">{questions.map((question) => {
          const answered = isAnswered(values[question.id]);
          const flagged = Boolean(flags[question.id]);
          const current = activeQuestionId === question.id;
          return <div key={question.id} data-nav-question-id={question.id} className={`exam-question-chip ${answered ? "answered" : "unanswered"} ${flagged ? "flagged" : ""} ${current ? "current" : ""}`}>
            <button ref={(element) => { if (element) questionChips.current.set(question.id, element); else questionChips.current.delete(question.id); }} type="button" className="exam-question-number" onClick={() => navigateToQuestion(question.id, question.passageIndex)} aria-label={`Go to question ${question.number}`} aria-current={current ? "true" : undefined}>{question.number}</button>
            <button type="button" className="exam-question-flag" onClick={() => void toggleFlag(question.id)} aria-label={`${flagged ? "Unflag" : "Flag"} question ${question.number}`} aria-pressed={flagged}><span aria-hidden="true">{flagged ? "⚑" : "⚐"}</span></button>
          </div>;
        })}</nav>
      </div>
      <button type="button" onClick={() => void submit()} disabled={submitting} className="exam-submit">{submitting ? "Submitting…" : "Submit answers"}</button>
    </footer>
    <ConfirmDialog open={confirmDeleteAll} title="Delete all highlights?" description="All highlights in this attempt will be removed. This action cannot be undone." confirmLabel="Delete all highlights" pending={deletingAll} errorMessage={highlightError} onCancel={() => { setConfirmDeleteAll(false); setHighlightError(""); }} onConfirm={() => { if (stopped.current) return; setDeletingAll(true); setHighlightError(""); void runMutation(() => deleteAllHighlights(attemptId)).then(() => { setHighlights([]); setConfirmDeleteAll(false); }).catch((error) => { if (!(error instanceof AttemptStoppedError)) setHighlightError("Could not delete the highlights. Please try again."); }).finally(() => setDeletingAll(false)); }} />
  </div>;
}

function isAnswered(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return value !== null && value !== undefined && value !== "";
}

function PassagePane({ passage, highlighting }: { passage: ExamPassage; highlighting: HighlightController }) {
  return <article className="exam-passage"><div className="exam-passage-content"><p className="exam-passage-kicker">Reading passage {passage.order_index + 1}</p><h2>{passage.title}</h2><div className="exam-passage-body">{passage.blocks.map((block) => { const text = <SelectableText text={block.text} target={{ target_kind: "PASSAGE_BLOCK", target_id: passage.id, segment_id: block.id }} controller={highlighting} />; return block.type === "heading" ? <h3 key={block.id}>{text}</h3> : <p key={block.id} className="exam-passage-paragraph"><b>{block.label}</b>{text}</p>; })}</div></div></article>;
}
