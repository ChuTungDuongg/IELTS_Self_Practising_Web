"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { PauseAttemptControl } from "@/features/exam/pause-attempt-control";
import { elapsedFromSnapshot, estimateServerOffset, formatDuration, remainingSeconds } from "@/features/exam/timer";
import { QuestionGroupInstruction } from "@/features/questions/question-group-instruction";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { recordActivity, recordNavigation, saveAnswer } from "@/lib/api/attempts";
import { assetContentUrl } from "@/lib/api/assets";
import { getExam, saveFlag, submitAttempt, type ExamPayload } from "@/lib/api/exam";
import { ListeningAudioPlayer } from "./audio-player";

export function ListeningRunner({ initial }: { initial: ExamPayload }) {
  const router = useRouter();
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
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [clock, setClock] = useState(() => Date.now());
  const dirty = useRef(new Map<string, unknown>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const finalized = useRef(false);
  const lastActivity = useRef(0);
  const lastHeartbeat = useRef(0);
  const questionPane = useRef<HTMLElement>(null);
  const questionChips = useRef(new Map<string, HTMLButtonElement>());
  const pendingQuestion = useRef<string | null>(null);
  const offset = useMemo(() => estimateServerOffset(initial.attempt.server_time), [initial.attempt.server_time]);

  const persist = useCallback(async (id: string, value: unknown) => {
    setSaveState("saving");
    try {
      await saveAnswer(attemptId, id, value);
      dirty.current.delete(id);
      setSaveState("saved");
      return true;
    } catch {
      setSaveState("error");
      return false;
    }
  }, [attemptId]);

  function answer(id: string, value: string | string[]) {
    setValues((current) => ({ ...current, [id]: value }));
    setActiveQuestionId(id);
    dirty.current.set(id, value);
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.set(id, setTimeout(() => persist(id, value), 400));
  }

  const flush = useCallback(async () => {
    timers.current.forEach(clearTimeout);
    timers.current.clear();
    const saved = await Promise.all([...dirty.current].map(([id, value]) => persist(id, value)));
    if (saved.some((result) => !result)) throw new Error("Pending answers could not be saved.");
  }, [persist]);

  useEffect(() => {
    const timerMap = timers.current;
    const interval = window.setInterval(() => void flush(), 10_000);
    const ticker = window.setInterval(() => setClock(Date.now()), 1000);
    return () => {
      clearInterval(interval);
      clearInterval(ticker);
      timerMap.forEach(clearTimeout);
    };
  }, [flush]);

  useEffect(() => {
    const meaningful = () => {
      const now = Date.now();
      lastActivity.current = now;
      if (now - lastHeartbeat.current > 20_000) {
        lastHeartbeat.current = now;
        void recordActivity(attemptId);
      }
    };
    const events: Array<keyof WindowEventMap> = ["keydown", "click", "touchstart", "scroll"];
    events.forEach((event) => window.addEventListener(event, meaningful, { passive: true }));
    const afk = window.setInterval(() => {
      if (Date.now() - lastActivity.current > 300_000) void getExam(attemptId).finally(() => router.refresh());
    }, 5000);
    return () => {
      events.forEach((event) => window.removeEventListener(event, meaningful));
      clearInterval(afk);
    };
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
  }, [partIndex, activeQuestionId, scrollToQuestion]);

  useEffect(() => {
    if (!activeQuestionId) return;
    const chip = questionChips.current.get(activeQuestionId);
    if (chip && typeof chip.scrollIntoView === "function") chip.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeQuestionId]);

  useEffect(() => {
    const pane = questionPane.current;
    if (!pane || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
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
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0]?.target as HTMLElement | undefined;
      const questionId = (centered ?? visible)?.dataset.questionId;
      if (questionId) setActiveQuestionId(questionId);
    }, { root: pane, threshold: [0.35, 0.65] });
    pane.querySelectorAll(".exam-question-target[data-question-id]").forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [partIndex, activeQuestionId]);

  const seconds = initial.attempt.timer_mode === "COUNTDOWN" && initial.attempt.deadline_at
    ? remainingSeconds(initial.attempt.deadline_at, offset, clock)
    : elapsedFromSnapshot(initial.attempt.elapsed_seconds, initial.attempt.server_time, offset, clock);
  const completionPath = initial.attempt.test_session_id ? `/test-session/${initial.attempt.test_session_id}` : `/review/${attemptId}`;
  const part = parts[partIndex];
  const partGroups = useMemo(
    () => part ? [...part.question_groups].sort((left, right) => left.order_index - right.order_index) : [],
    [part],
  );
  const activeGroup = partGroups.find((group) => group.questions.some((question) => question.id === activeQuestionId)) ?? partGroups[0];
  const visualGroup = activeGroup ? ["map_labelling", "plan_labelling", "diagram_labelling"].includes(activeGroup.question_type) : false;

  useEffect(() => {
    if (part) void recordNavigation(attemptId, "LISTENING_PART", part.id).catch(() => undefined);
  }, [attemptId, part]);
  useEffect(() => {
    if (activeQuestionId) void recordNavigation(attemptId, "QUESTION", activeQuestionId).catch(() => undefined);
  }, [activeQuestionId, attemptId]);
  useEffect(() => {
    if (initial.attempt.timer_mode === "COUNTDOWN" && seconds === 0 && !finalized.current) {
      finalized.current = true;
      void flush().finally(() => submitAttempt(attemptId).finally(() => router.push(completionPath)));
    }
  }, [attemptId, completionPath, flush, initial.attempt.timer_mode, router, seconds]);

  if (!part) return <p>No Listening part is available.</p>;

  async function toggleFlag(id: string) {
    const next = !flags[id];
    setFlags((current) => ({ ...current, [id]: next }));
    await saveFlag(attemptId, id, next);
  }

  async function submit() {
    await flush();
    await submitAttempt(attemptId);
    router.push(completionPath);
  }

  function selectPart(index: number) {
    pendingQuestion.current = null;
    setPartIndex(index);
    setActiveQuestionId(questions.find((question) => question.partIndex === index)?.id ?? null);
    if (questionPane.current) questionPane.current.scrollTop = 0;
  }

  function navigateToQuestion(questionId: string, ownerPartIndex: number) {
    const target = questions.find((question) => question.id === questionId);
    const currentGroupId = activeGroup?.id;
    if (ownerPartIndex !== partIndex || target?.groupId !== currentGroupId) pendingQuestion.current = questionId;
    setActiveQuestionId(questionId);
    if (ownerPartIndex !== partIndex) {
      setPartIndex(ownerPartIndex);
      return;
    }
    if (target?.groupId === currentGroupId) scrollToQuestion(questionId);
  }

  return <div className="exam-runner listening-exam">
    <header className="exam-header"><div><p>LISTENING · SECTION {part.order_index + 1}</p><h1>{initial.test_title}</h1></div><div className="exam-header-tools"><PauseAttemptControl attemptId={attemptId} beforePause={flush} /><ThemeToggle /><div className="exam-header-status"><span className={`exam-timer ${initial.attempt.timer_mode === "COUNTDOWN" && seconds < 300 ? "exam-timer-warning" : ""}`}>{formatDuration(seconds)}</span><span className={`exam-save-state exam-save-${saveState}`}>{saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : "Saved"}</span></div></div></header>
    {initial.listening_audio_asset ? <><ListeningAudioPlayer src={assetContentUrl(initial.listening_audio_asset)} policy={{ allowSeeking: initial.audio_policy?.allow_seeking ?? true, allowSpeed: initial.audio_policy?.allow_speed ?? true }} />{initial.audio_policy?.allow_seeking === false ? <p className="exam-mode-label">Exam mode · Seeking locked</p> : null}</> : <p className="notice m-4">This Listening test has no audio recording attached.</p>}
    <main ref={questionPane} className={`listening-question-pane ${visualGroup ? "listening-question-pane-visual" : ""}`} onFocusCapture={(event) => {
      const target = (event.target as HTMLElement).closest<HTMLElement>(".exam-question-target[data-question-id]");
      if (target?.dataset.questionId) setActiveQuestionId(target.dataset.questionId);
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
        <nav className="exam-question-strip" aria-label="Question navigation">{questions.map((question) => {
          const answered = isAnswered(values[question.id]);
          const flagged = Boolean(flags[question.id]);
          const current = activeQuestionId === question.id;
          return <div key={question.id} data-nav-question-id={question.id} className={`exam-question-chip ${answered ? "answered" : "unanswered"} ${flagged ? "flagged" : ""} ${current ? "current" : ""}`}>
            <button ref={(element) => { if (element) questionChips.current.set(question.id, element); else questionChips.current.delete(question.id); }} type="button" className="exam-question-number" onClick={() => navigateToQuestion(question.id, question.partIndex)} aria-label={`Go to question ${question.number}`} aria-current={current ? "true" : undefined}>{question.number}</button>
            <button type="button" className="exam-question-flag" onClick={() => void toggleFlag(question.id)} aria-label={`${flagged ? "Unflag" : "Flag"} question ${question.number}`} aria-pressed={flagged}><span aria-hidden="true">{flagged ? "⚑" : "⚐"}</span></button>
          </div>;
        })}</nav>
      </div>
      <button type="button" onClick={() => void submit()} className="exam-submit">Submit answers</button>
    </footer>
  </div>;
}

function isAnswered(value: unknown): boolean {
  if (Array.isArray(value)) return value.length > 0;
  return value !== null && value !== undefined && value !== "";
}
