"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { AttemptStoppedError, useAttemptLifecycle } from "@/features/exam/attempt-lifecycle";
import { RevisionAutosaveQueue, useRevisionAutosave } from "@/features/exam/revision-autosave";
import { useExamSubmit } from "@/features/exam/use-exam-submit";
import { revealQuestionChip, scrollQuestionIntoPane } from "@/features/exam/question-navigation";
import { elapsedFromSnapshot, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { recordActivity, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { getExam, saveFlag, type ExamPayload } from "@/lib/api/exam";
import { ListeningAudioPlayer } from "./audio-player";

export function ListeningRunner({ initial }: { initial: ExamPayload }) {
  const attemptId = initial.attempt.attempt_id;
  const parts = useMemo(
    () => [...initial.listening_parts].sort((left, right) => left.order_index - right.order_index),
    [initial.listening_parts],
  );
  const questions = useMemo(() => parts.flatMap((part, partIndex) => [...part.question_groups]
    .sort((left, right) => left.order_index - right.order_index)
    .flatMap((group) => [...group.questions]
      .sort((left, right) => left.order_index - right.order_index)
      .map((question) => ({ ...question, partIndex, groupId: group.id })))), [parts]);
  const [partIndex, setPartIndex] = useState(0);
  const [values, setValues] = useState<Record<string, unknown>>(() => Object.fromEntries(questions.map((question) => [question.id, question.value])));
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(questions.map((question) => [question.id, question.flagged])));
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(() => questions[0]?.id ?? null);
  const [actionError, setActionError] = useState("");
  const [clock, setClock] = useState(() => Date.now());
  const autosaveRef = useRef<RevisionAutosaveQueue<unknown> | null>(null);
  const answerRevisions = useRef<Record<string, number>>(Object.fromEntries(questions.map((question) => [question.id, question.answer_revision])));
  const finalized = useRef(false);
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const questionPane = useRef<HTMLElement>(null);
  const questionStrip = useRef<HTMLElement>(null);
  const questionChips = useRef(new Map<string, HTMLButtonElement>());
  const pendingQuestion = useRef<string | null>(null);
  const programmaticNavigation = useRef<string | null>(null);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);
  const { stopped, ended, accept, runMutation, isStopped } = useAttemptLifecycle(attemptId, () => {
    autosaveRef.current?.stop();
  });
  const sendAnswer = useCallback(
    async (id: string, value: unknown) => {
      const response = await runMutation(() => saveAnswer(attemptId, id, value, answerRevisions.current[id] ?? 0));
      answerRevisions.current[id] = response.revision;
    },
    [attemptId, runMutation],
  );
  const { queue: autosave, status: saveState } = useRevisionAutosave<unknown>(
    sendAnswer, 400,
  );
  useEffect(() => { autosaveRef.current = autosave; }, [autosave]);
  const flush = useCallback(() => autosave.flush(), [autosave]);
  const { submit, submitting, finalizing, submitError, isFinalizing } = useExamSubmit({
    attemptId, initialAttempt: initial.attempt, flush, runMutation, accept, isStopped,
  });

  function answer(id: string, value: string | string[]) {
    if (stopped.current || isFinalizing()) return;
    programmaticNavigation.current = null;
    setValues((current) => ({ ...current, [id]: value }));
    setActiveQuestionId(id);
    autosave.markDirty(id, value);
  }

  useEffect(() => {
    const interval = window.setInterval(() => { if (!stopped.current) void flush().catch(() => undefined); }, 10_000);
    const ticker = window.setInterval(() => setClock(Date.now()), 1000);
    return () => {
      clearInterval(interval);
      clearInterval(ticker);
    };
  }, [flush, stopped]);

  useEffect(() => {
    const meaningful = () => {
      if (stopped.current) return;
      const now = Date.now();
      lastActivity.current = now;
      if (now - lastHeartbeat.current > 20_000) {
        lastHeartbeat.current = now;
        void runMutation(() => recordActivity(attemptId)).catch(() => undefined);
      }
    };
    const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, meaningful, { passive: true }));
    const afk = window.setInterval(() => {
      if (!stopped.current && Date.now() - lastActivity.current > 300_000) void getExam(attemptId).then((exam) => accept(exam.attempt)).catch(() => undefined);
    }, 5000);
    return () => {
      events.forEach((event) => window.removeEventListener(event, meaningful));
      clearInterval(afk);
    };
  }, [accept, attemptId, runMutation, stopped]);

  const holdNavigation = useCallback((questionId: string | null) => {
    // Keep late observer entries from replacing a deliberate navigator choice.
    // Manual pane interaction releases the guard before visibility tracking resumes.
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
    if (!activeQuestionId || !questionStrip.current) return;
    const chip = questionChips.current.get(activeQuestionId);
    if (chip) revealQuestionChip(questionStrip.current, chip);
  }, [activeQuestionId]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at
    ? remainingSeconds(initial.attempt.deadline_at, offset, clock)
    : elapsedFromSnapshot(initial.attempt.elapsed_seconds, initial.attempt.server_time, offset, clock);
  const part = parts[partIndex];
  const partGroups = useMemo(
    () => part ? [...part.question_groups].sort((left, right) => left.order_index - right.order_index) : [],
    [part],
  );
  const activeGroup = partGroups.find((group) => group.questions.some((question) => question.id === activeQuestionId)) ?? partGroups[0];
  const visualGroup = activeGroup ? ["map_labelling", "plan_labelling", "diagram_labelling"].includes(activeGroup.question_type) : false;

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
  }, [activeGroup?.id, holdNavigation, partIndex, scrollToQuestion]);

  useEffect(() => {
    const pane = questionPane.current;
    if (!pane || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      if (programmaticNavigation.current || pendingQuestion.current) return;
      const paneRect = pane.getBoundingClientRect();
      const paneCenter = paneRect.top + paneRect.height / 2;
      const centered = paneRect.height > 0
        ? [...pane.querySelectorAll<HTMLElement>(".exam-question-target[data-question-id]")]
          .map((target) => ({ target, rect: target.getBoundingClientRect() }))
          .filter(({ rect }) => rect.bottom > paneRect.top && rect.top < paneRect.bottom)
          .sort((left, right) => (
            Math.abs((left.rect.top + left.rect.bottom) / 2 - paneCenter)
            - Math.abs((right.rect.top + right.rect.bottom) / 2 - paneCenter)
          ))[0]?.target
        : undefined;
      const visible = entries
        .filter((entry) => entry.isIntersecting && pane.contains(entry.target))
        .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0]?.target as HTMLElement | undefined;
      const questionId = (centered ?? visible)?.dataset.questionId;
      if (questionId) setActiveQuestionId(questionId);
    }, { root: pane, threshold: [0.35, 0.65] });
    pane.querySelectorAll(".exam-question-target[data-question-id]").forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [activeGroup?.id, partIndex]);

  useEffect(() => {
    if (part && !stopped.current) void runMutation(() => recordNavigation(attemptId, "LISTENING_PART", part.id)).catch(() => undefined);
  }, [attemptId, part, runMutation, stopped]);
  useEffect(() => {
    if (activeQuestionId && !stopped.current) void runMutation(() => recordNavigation(attemptId, "QUESTION", activeQuestionId)).catch(() => undefined);
  }, [activeQuestionId, attemptId, runMutation, stopped]);
  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current && !stopped.current) {
      finalized.current = true;
      void submit();
    }
  });

  if (ended) return <p role="status">Attempt finished. Opening your result…</p>;
  if (!part) return <p>No Listening part is available.</p>;

  async function toggleFlag(id: string) {
    if (stopped.current) return;
    const next = !flags[id];
    setFlags((current) => ({ ...current, [id]: next }));
    try { await runMutation(() => saveFlag(attemptId, id, next)); } catch (error) { if (!(error instanceof AttemptStoppedError)) setActionError("Could not save the flag. Please try again."); }
  }

  function selectPart(index: number) {
    pendingQuestion.current = null;
    const firstQuestionId = questions.find((question) => question.partIndex === index)?.id ?? null;
    holdNavigation(firstQuestionId);
    setPartIndex(index);
    setActiveQuestionId(firstQuestionId);
    if (questionPane.current) questionPane.current.scrollTop = 0;
  }

  function navigateToQuestion(questionId: string, ownerPartIndex: number) {
    const target = questions.find((question) => question.id === questionId);
    const currentGroupId = activeGroup?.id;
    holdNavigation(questionId);
    if (ownerPartIndex !== partIndex || target?.groupId !== currentGroupId) pendingQuestion.current = questionId;
    setActiveQuestionId(questionId);
    if (ownerPartIndex !== partIndex) {
      setPartIndex(ownerPartIndex);
      return;
    }
    if (target?.groupId === currentGroupId && !scrollToQuestion(questionId)) pendingQuestion.current = questionId;
  }

  return <div className="exam-runner listening-exam">
    <header className="exam-header"><div><p>LISTENING · SECTION {part.order_index + 1}</p><h1>{initial.test_title}</h1></div><div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flush} /><ThemeToggle /><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "conflict" ? "This response changed in another tab or session." : saveState === "error" ? "Save failed" : saveState === "dirty" ? "Unsaved" : "Saved"}</span>{saveState === "error" ? <button type="button" onClick={() => void flush().catch(() => undefined)}>Retry save</button> : null}{saveState === "conflict" ? <button type="button" onClick={() => window.location.reload()}>Reload latest</button> : null}</div></div></header>
    {submitError ? <p role="alert" className="notice notice-error">{submitError}</p> : null}
    {actionError ? <p role="alert" className="notice notice-error">{actionError}</p> : null}
    {initial.listening_audio_asset ? <><ListeningAudioPlayer src={assetContentUrl(initial.listening_audio_asset)} policy={{ allowSeeking: initial.audio_policy?.allow_seeking ?? true, allowSpeed: initial.audio_policy?.allow_speed ?? true }} />{initial.audio_policy?.allow_seeking === false ? <p className="exam-mode-label">Exam mode · Seeking locked</p> : null}</> : <p className="notice m-4">This Listening test has no audio recording attached.</p>}
    <main ref={questionPane} inert={finalizing} className={`listening-question-pane ${visualGroup ? "listening-question-pane-visual" : ""}`} onWheelCapture={() => { programmaticNavigation.current = null; }} onTouchStartCapture={() => { programmaticNavigation.current = null; }} onPointerDownCapture={() => { programmaticNavigation.current = null; }} onKeyDownCapture={() => { programmaticNavigation.current = null; }} onFocusCapture={(event) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(".exam-question-target[data-question-id]");
      if (target?.dataset.questionId) { programmaticNavigation.current = null; setActiveQuestionId(target.dataset.questionId); }
    }}>
      <div className="listening-question-heading"><div><p>Listening · Section {part.order_index + 1}</p><h2>{part.title}</h2></div><span>{activeGroup ? `Questions ${Math.min(...activeGroup.questions.map((question) => question.number))}–${Math.max(...activeGroup.questions.map((question) => question.number))}` : "No questions"}</span></div>
      {activeGroup ? (() => {
        const definition = questionRegistry[activeGroup.question_type as keyof typeof questionRegistry];
        if (!definition) return null;
        const Renderer = definition.ExamRenderer;
        return <section key={activeGroup.id} data-question-group-id={activeGroup.id} className={`exam-question-group ${visualGroup ? "listening-visual-question-group" : ""}`}>
          <QuestionGroupInstruction group={activeGroup as ExamGroup} />
          <Renderer group={{ ...activeGroup, questions: [...activeGroup.questions].sort((left, right) => left.order_index - right.order_index) } as ExamGroup} values={values} onAnswer={answer} activeQuestionId={activeQuestionId} presentation={visualGroup ? "listening-visual" : "default"} />
        </section>;
      })() : <p className="notice">This Section has no question groups.</p>}
    </main>
    <footer className="exam-footer listening-exam-footer">
      <div className="exam-footer-navigation">
        <nav className="exam-section-navigation" aria-label="Section navigation">{parts.map((item, index) => <button key={item.id} type="button" onClick={() => selectPart(index)} className={index === partIndex ? "active" : ""} aria-current={index === partIndex ? "page" : undefined}>Section {item.order_index + 1}</button>)}</nav>
        <nav ref={questionStrip} className="exam-question-strip" aria-label="Question navigation">{questions.map((question) => {
          const answered = isAnswered(values[question.id]);
          const flagged = Boolean(flags[question.id]);
          const current = activeQuestionId === question.id;
          return <div key={question.id} data-nav-question-id={question.id} className={`exam-question-chip ${answered ? "answered" : "unanswered"} ${flagged ? "flagged" : ""} ${current ? "current" : ""}`}>
            <button ref={(element) => { if (element) questionChips.current.set(question.id, element); else questionChips.current.delete(question.id); }} type="button" className="exam-question-number" onClick={() => navigateToQuestion(question.id, question.partIndex)} aria-label={`Go to question ${question.number}`} aria-current={current ? "true" : undefined}>{question.number}</button>
            <button type="button" className="exam-question-flag" onClick={() => void toggleFlag(question.id)} aria-label={`${flagged ? "Unflag" : "Flag"} question ${question.number}`} aria-pressed={flagged}><span aria-hidden="true">{flagged ? "⚑" : "⚐"}</span></button>
          </div>;
        })}</nav>
      </div>
      <button type="button" onClick={() => void submit()} disabled={submitting} className="exam-submit">{submitting ? "Submitting…" : "Submit answers"}</button>
    </footer>
  </div>;
}

function isAnswered(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return value !== null && value !== undefined && value !== "";
}
