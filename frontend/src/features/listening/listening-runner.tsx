"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { AttemptStoppedError, useAttemptLifecycle } from "@/features/exam/attempt-lifecycle";
import { RevisionAutosaveQueue } from "@/features/exam/revision-autosave";
import { useExamDraftAutosave } from "@/features/exam/use-exam-draft-autosave";
import { DraftRecoveryNotices } from "@/features/exam/draft-recovery-notices";
import { useExamSubmit } from "@/features/exam/use-exam-submit";
import { revealQuestionChip, scrollQuestionIntoPane } from "@/features/exam/question-navigation";
import { elapsedFromSnapshot, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";
import type { HighlightController } from "@/features/highlighting/selectable-text";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import { completedQuestionSlots, groupQuestionRange, questionSpan } from "@/features/questions/numbering";
import type { ExamGroup } from "@/features/questions/types";
import { recordActivity, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { createHighlight, deleteAllHighlights, deleteHighlight, getExam, saveFlag, type ExamPayload, type HighlightCreate } from "@/lib/api/exam";
import { focusedUnitLabel } from "@/features/exam/focused-attempt";
import { sectionAudioClip } from "./audio-time";
import { ListeningAudioPlayer } from "./audio-player";

export function ListeningRunner({ initial }: { initial: ExamPayload }) {
  const { t } = useTranslation();
  const attemptId = initial.attempt.attempt_id;
  const focused = initial.attempt.scope === "FOCUSED_UNIT";
  const parts = useMemo(
    () => [...initial.listening_parts].sort((left, right) => left.order_index - right.order_index),
    [initial.listening_parts],
  );
  const questions = useMemo(() => parts.flatMap((part, partIndex) => [...part.question_groups]
    .sort((left, right) => left.order_index - right.order_index)
    .flatMap((group) => [...group.questions]
      .sort((left, right) => left.order_index - right.order_index)
      .map((question) => ({ ...question, partIndex, groupId: group.id, questionType: group.question_type })))), [parts]);
  const navigationSlots = useMemo(() => questions.flatMap((question) => Array.from(
    { length: questionSpan(question.questionType, question.config) },
    (_, slotIndex) => ({ ...question, number: question.number + slotIndex, slotIndex }),
  )), [questions]);
  const [partIndex, setPartIndex] = useState(0);
  const initialResponses = useMemo(() => questions.map((question) => ({ id: question.id, value: question.value, revision: question.answer_revision })), [questions]);
  const [flags, setFlags] = useState<Record<string, boolean>>(() => Object.fromEntries(questions.map((question) => [question.id, question.flagged])));
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(() => questions[0]?.id ?? null);
  const [actionError, setActionError] = useState<import("@/lib/i18n/types").TranslationKey | "">("");
  const [highlights, setHighlights] = useState(() => initial.highlights);
  const [highlightError, setHighlightError] = useState<import("@/lib/i18n/types").TranslationKey | "">("");
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [clock, setClock] = useState(() => Date.now());
  const autosaveRef = useRef<RevisionAutosaveQueue<unknown> | null>(null);
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
    (id: string, value: unknown, revision: number) => runMutation(() => saveAnswer(attemptId, id, value, revision)),
    [attemptId, runMutation],
  );
  const { queue: autosave, status: saveState, offline, values, conflicts, edit, resolveConflict, flush } = useExamDraftAutosave<unknown>({
    attempt: initial.attempt, initialResponses, save: sendAnswer, debounceMs: 400,
  });
  useEffect(() => { autosaveRef.current = autosave; }, [autosave]);
  const { submit, submitting, finalizing, submitError, isFinalizing } = useExamSubmit({
    attemptId, initialAttempt: initial.attempt, flush, runMutation, accept, isStopped,
  });

  function answer(id: string, value: string | string[]) {
    if (stopped.current || isFinalizing()) return;
    programmaticNavigation.current = null;
    if (!edit(id, value)) return;
    setActiveQuestionId(id);
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

  if (ended) return <p role="status">{t("runner.finished")}</p>;
  if (!part) return <p>{t("runner.noListening")}</p>;
  const playbackClip = focused ? sectionAudioClip(part) : undefined;

  async function toggleFlag(id: string) {
    if (stopped.current) return;
    const next = !flags[id];
    setFlags((current) => ({ ...current, [id]: next }));
    try { await runMutation(() => saveFlag(attemptId, id, next)); } catch (error) { if (!(error instanceof AttemptStoppedError)) setActionError("runner.flagError"); }
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

  async function addHighlight(body: HighlightCreate) {
    if (stopped.current) return;
    setHighlightError("");
    try {
      const created = await runMutation(() => createHighlight(attemptId, body));
      setHighlights((current) => [...current, created]);
    } catch (error) {
      if (!(error instanceof AttemptStoppedError)) setHighlightError("runner.highlightSaveError");
    }
  }

  async function removeHighlight(id: string) {
    if (stopped.current) return;
    setHighlightError("");
    try {
      await runMutation(() => deleteHighlight(attemptId, id));
      setHighlights((current) => current.filter((item) => item.id !== id));
    } catch (error) {
      if (!(error instanceof AttemptStoppedError)) setHighlightError("runner.highlightDeleteError");
    }
  }

  const highlighting: HighlightController = { highlights, onCreate: addHighlight, onDelete: removeHighlight };

  return <div className="exam-runner listening-exam listening-attempt">
    <header className="exam-header"><div><p>{focused ? t("runner.listeningFocused") : t("runner.listeningSectionUpper", { number: part.order_index + 1 })}</p><h1>{initial.test_title}</h1>{focusedUnitLabel(initial.attempt, t) ? <p>{focusedUnitLabel(initial.attempt, t)}</p> : null}</div><div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flush} /><ThemeToggle /><div className="exam-highlight-toolbar" aria-label={t("runner.highlightManagement")}><span>{t(highlights.length === 1 ? "runner.highlightCount" : "runner.highlightsCount", { count: highlights.length })}</span>{highlights.length ? <button type="button" onClick={() => { setHighlightError(""); setConfirmDeleteAll(true); }}>{t("runner.deleteAll")}</button> : null}</div><div className="exam-header-status"><span aria-label={t(initial.attempt.timer_mode === "COUNTDOWN" ? "runner.timeRemaining" : "runner.timeElapsed")} className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? t("common.saving") : saveState === "conflict" ? t("runner.conflict") : saveState === "error" ? t("runner.saveFailed") : saveState === "dirty" ? t("runner.unsaved") : t("common.saved")}</span>{saveState === "error" ? <button type="button" onClick={() => void flush().catch(() => undefined)}>{t("runner.retry")}</button> : null}{saveState === "conflict" ? <button type="button" onClick={() => window.location.reload()}>{t("runner.reload")}</button> : null}</div></div></header>
    {submitError ? <p role="alert" className="notice notice-error">{submitError}</p> : null}
    <DraftRecoveryNotices offline={offline} conflicts={conflicts} labelFor={(id) => t("runner.questionLower", { number: questions.find((question) => question.id === id)?.number ?? id })} onResolve={resolveConflict} />
    {actionError ? <p role="alert" className="notice notice-error">{t(actionError)}</p> : null}
    {highlightError && !confirmDeleteAll ? <p role="alert" className="notice notice-error">{t(highlightError)}</p> : null}
    {!initial.listening_audio_asset ? <p className="notice m-4">{focused ? t("runner.externalRecordingNotice") : t("runner.noRecording")}</p> : null}
    <main ref={questionPane} inert={finalizing} className={`listening-question-pane ${visualGroup ? "listening-question-pane-visual" : ""}`} onWheelCapture={() => { programmaticNavigation.current = null; }} onTouchStartCapture={() => { programmaticNavigation.current = null; }} onPointerDownCapture={() => { programmaticNavigation.current = null; }} onKeyDownCapture={() => { programmaticNavigation.current = null; }} onFocusCapture={(event) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(".exam-question-target[data-question-id]");
      if (target?.dataset.questionId) { programmaticNavigation.current = null; setActiveQuestionId(target.dataset.questionId); }
    }}>
      <div className="listening-question-heading"><div><p>{t("runner.listeningSection", { number: part.order_index + 1 })}</p><h2>{part.title}</h2></div><span>{activeGroup ? groupQuestionRange(activeGroup).replace(/^Q/, `${t("common.questions")} `) : t("runner.noQuestions")}</span></div>
      {activeGroup ? (() => {
        const definition = questionRegistry[activeGroup.question_type as keyof typeof questionRegistry];
        if (!definition) return null;
        const Renderer = definition.ExamRenderer;
        return <section key={activeGroup.id} data-question-group-id={activeGroup.id} className={`exam-question-group ${visualGroup ? "listening-visual-question-group" : ""}`}>
          <QuestionGroupInstruction group={activeGroup as ExamGroup} />
          <Renderer group={{ ...activeGroup, questions: [...activeGroup.questions].sort((left, right) => left.order_index - right.order_index) } as ExamGroup} values={values} onAnswer={answer} highlighting={highlighting} activeQuestionId={activeQuestionId} presentation={visualGroup ? "listening-visual" : "default"} />
        </section>;
      })() : <p className="notice">{t("runner.noGroups")}</p>}
    </main>
    <div className="listening-lower-dock">
      {initial.listening_audio_asset ? <div className="listening-audio-dock">
        <ListeningAudioPlayer layout="exam-bar" src={assetContentUrl(initial.listening_audio_asset)} clip={playbackClip} policy={{ allowSeeking: initial.audio_policy?.allow_seeking ?? true, allowSpeed: initial.audio_policy?.allow_speed ?? true }} />
        {focused && !playbackClip ? <p className="notice m-4">{t("runner.fullRecordingNotice")}</p> : null}
        {initial.audio_policy?.allow_seeking === false ? <p className="exam-mode-label">{t("runner.seekingLocked")}</p> : null}
      </div> : null}
    <footer className="exam-footer listening-exam-footer">
      <div className="exam-footer-navigation">
        {!focused ? <nav className="exam-section-navigation" aria-label={t("runner.sectionNavigation")}>{parts.map((item, index) => <button key={item.id} type="button" onClick={() => selectPart(index)} className={index === partIndex ? "active" : ""} aria-current={index === partIndex ? "page" : undefined}>{t("common.sectionNumber", { number: item.order_index + 1 })}</button>)}</nav> : null}
        <nav ref={questionStrip} className="exam-question-strip" aria-label={t("runner.questionNavigation")}>{navigationSlots.map((question) => {
          const answered = completedQuestionSlots(question.questionType, question.config, values[question.id]) > question.slotIndex;
          const flagged = Boolean(flags[question.id]);
          const current = activeQuestionId === question.id;
          return <div key={`${question.id}:${question.slotIndex}`} data-nav-question-id={question.id} className={`exam-question-chip ${answered ? "answered" : "unanswered"} ${flagged ? "flagged" : ""} ${current ? "current" : ""}`}>
            <button ref={question.slotIndex === 0 ? (element) => { if (element) questionChips.current.set(question.id, element); else questionChips.current.delete(question.id); } : undefined} type="button" className="exam-question-number" onClick={() => navigateToQuestion(question.id, question.partIndex)} aria-label={t("runner.goQuestion", { number: question.number })} aria-current={current ? "true" : undefined}>{question.number}</button>
            <button type="button" className="exam-question-flag" onClick={() => void toggleFlag(question.id)} aria-label={t(flagged ? "runner.unflagQuestion" : "runner.flagQuestion", { number: question.number })} aria-pressed={flagged}><span aria-hidden="true">{flagged ? "⚑" : "⚐"}</span></button>
          </div>;
        })}</nav>
      </div>
      <button type="button" onClick={() => void submit()} disabled={submitting} className="exam-submit">{submitting ? t("runner.submitting") : t("runner.submitAnswers")}</button>
    </footer>
    </div>
    <ConfirmDialog open={confirmDeleteAll} title={t("runner.deleteHighlightsTitle")} description={t("runner.deleteHighlightsDescription")} confirmLabel={t("runner.deleteHighlights")} pending={deletingAll} errorMessage={highlightError ? t(highlightError) : ""} onCancel={() => { setConfirmDeleteAll(false); setHighlightError(""); }} onConfirm={() => { if (stopped.current) return; setDeletingAll(true); setHighlightError(""); void runMutation(() => deleteAllHighlights(attemptId)).then(() => { setHighlights([]); setConfirmDeleteAll(false); }).catch((error) => { if (!(error instanceof AttemptStoppedError)) setHighlightError("runner.highlightsDeleteError"); }).finally(() => setDeletingAll(false)); }} />
  </div>;
}
