"use client";

import { saveAssignmentWritingScore } from "@/lib/api/classroom-results";
import type { AssignmentGradingScope } from "@/lib/api/grading";
import { useTranslation } from "@/lib/i18n/locale-provider";

import { useCallback, useRef, useState } from "react";
import Image from "next/image";
import { useAuth } from "@/features/auth/auth-provider";
import { WritingAIAssessment, type EssayAnnotationState } from "./writing-ai-assessment";
import { AnnotatedEssay } from "./annotated-essay";
import { presentAIFeedback } from "./ai-feedback-presentation";
import { aiTraits, type AIWritingResult } from "@/lib/api/writing-ai";
import { assetContentUrl } from "@/lib/api/assets";
import { focusedUnitLabel } from "@/features/exam/focused-attempt";
import {
  saveWritingTaskScore,
  type WritingReviewPayload,
} from "@/lib/api/exam";

const bands = Array.from({ length: 19 }, (_, index) => (index / 2).toFixed(1));
const criteria = [
  ["ta", "TA", "runner.criterion.ta"],
  ["cc", "CC", "runner.criterion.cc"],
  ["lr", "LR", "runner.criterion.lr"],
  ["gra", "GRA", "runner.criterion.gra"],
] as const;
type Criterion = "ta" | "cc" | "lr" | "gra";
type TaskSelection = Record<Criterion, string>;
type TaskFeedback = Record<Criterion, string>;

function initialSelections(data: WritingReviewPayload): Record<string, TaskSelection> {
  return Object.fromEntries(data.tasks.map((task) => [
    task.writing_task_id,
    {
      ta: task.score?.ta.toFixed(1) ?? "",
      cc: task.score?.cc.toFixed(1) ?? "",
      lr: task.score?.lr.toFixed(1) ?? "",
      gra: task.score?.gra.toFixed(1) ?? "",
    },
  ]));
}

function initialFeedback(data: WritingReviewPayload): Record<string, TaskFeedback> {
  return Object.fromEntries(data.tasks.map((task) => [
    task.writing_task_id,
    {
      ta: task.score?.ta_feedback ?? "",
      cc: task.score?.cc_feedback ?? "",
      lr: task.score?.lr_feedback ?? "",
      gra: task.score?.gra_feedback ?? "",
    },
  ]));
}

export function WritingReviewView({ data, readOnly = false, assignmentScope }: { data: WritingReviewPayload; readOnly?: boolean; assignmentScope?: AssignmentGradingScope }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [reviewData, setReviewData] = useState(data);
  const canEdit = !readOnly && reviewData.grading?.can_edit_final === true;
  const canCopy = canEdit && reviewData.grading?.can_copy_ai_to_final === true;
  const finalLabel = reviewData.grading?.context === "CLASSROOM" ? t("grading.teacherFinal") : t("grading.practiceFinal");
  const [taskIndex, setTaskIndex] = useState(0);
  const [selections, setSelections] = useState(() => initialSelections(data));
  const [feedback, setFeedback] = useState(() => initialFeedback(data));
  const [savingTaskId, setSavingTaskId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, { message: import("@/lib/i18n/types").TranslationKey; number?: number } | null>>({});
  const [errors, setErrors] = useState<Record<string, { message: import("@/lib/i18n/types").TranslationKey; number?: number } | null>>({});
  const task = reviewData.tasks[taskIndex];
  const focused = reviewData.review.attempt.scope === "FOCUSED_UNIT";
  const reviewRoot = useRef<HTMLDivElement>(null);
  const [essayState, setEssayState] = useState<EssayAnnotationState & { taskId: string } | null>(null);
  const selectedTaskId = task?.writing_task_id;
  const receiveAnnotations = useCallback((state: EssayAnnotationState) => {
    if (selectedTaskId) setEssayState({ ...state, taskId: selectedTaskId });
  }, [selectedTaskId]);
  const currentEssayState = !readOnly && essayState?.taskId === selectedTaskId ? essayState : null;

  function focusAnnotation(id: string) {
    const span = [...(reviewRoot.current?.querySelectorAll<HTMLElement>("[data-annotation-ids]") ?? [])]
      .find(element => element.dataset.annotationIds?.split(" ").includes(id));
    span?.scrollIntoView?.({ block: "center", behavior: "auto" }); span?.focus();
  }
  function focusFeedback(id: string) {
    const item = [...(reviewRoot.current?.querySelectorAll<HTMLElement>("[data-feedback-annotation-id]") ?? [])]
      .find(element => element.dataset.feedbackAnnotationId === id);
    item?.scrollIntoView?.({ block: "center", behavior: "auto" }); item?.focus();
  }

  if (!task) return <p>{t("runner.noWritingReview")}</p>;

  function updateCriterion(taskId: string, criterion: Criterion, value: string) {
    setSelections((current) => ({
      ...current,
      [taskId]: { ...current[taskId], [criterion]: value },
    }));
    setMessages((current) => ({ ...current, [taskId]: null }));
  }

  function updateFeedback(taskId: string, criterion: Criterion, value: string) {
    setFeedback((current) => ({
      ...current,
      [taskId]: { ...current[taskId], [criterion]: value },
    }));
    setMessages((current) => ({ ...current, [taskId]: null }));
  }

  function copyAISuggestions(taskId: string, result: AIWritingResult) {
    if (!canCopy) return;
    setSelections((current) => ({ ...current, [taskId]: Object.fromEntries(aiTraits.map((key) => [key, result.criteria[key].score.toFixed(1)])) as TaskSelection }));
    setFeedback((current) => ({ ...current, [taskId]: Object.fromEntries(aiTraits.map((key) => [key, presentAIFeedback(result.criteria[key].feedback)])) as TaskFeedback }));
    setMessages((current) => ({ ...current, [taskId]: { message: "runner.aiCopied" } }));
  }

  async function saveTaskScores(taskId: string, taskNumber: number) {
    if (!canEdit) return;
    const selection = selections[taskId];
    if (!selection || Object.values(selection).some((value) => value === "")) return;
    setSavingTaskId(taskId);
    setErrors((current) => ({ ...current, [taskId]: null }));
    setMessages((current) => ({ ...current, [taskId]: null }));
    try {
      const save = assignmentScope ? (attemptId: string, taskId: string, scores: import("@/lib/api/exam").WritingCriteriaInput) => saveAssignmentWritingScore(assignmentScope.classroomId, assignmentScope.assignmentId, attemptId, taskId, scores) : saveWritingTaskScore;
      const response = await save(
        reviewData.review.attempt.attempt_id,
        taskId,
        {
          ta: Number(selection.ta),
          cc: Number(selection.cc),
          lr: Number(selection.lr),
          gra: Number(selection.gra),
          ta_feedback: feedback[taskId]?.ta.trim() || null,
          cc_feedback: feedback[taskId]?.cc.trim() || null,
          lr_feedback: feedback[taskId]?.lr.trim() || null,
          gra_feedback: feedback[taskId]?.gra.trim() || null,
        },
      );
      setReviewData(response);
      setMessages((current) => ({ ...current, [taskId]: { message: "runner.taskScoresSaved", number: taskNumber } }));
    } catch {
      setErrors((current) => ({ ...current, [taskId]: { message: "runner.taskScoresError", number: taskNumber } }));
    } finally {
      setSavingTaskId(null);
    }
  }

  return <div ref={reviewRoot} className="writing-review">
    {reviewData.grading?.waiting_for_teacher ? <p className="notice" role="status">{t("grading.waiting")}</p> : null}
    {reviewData.grading?.context === "PERSONAL" ? <p>{t("grading.selfAssessed")}</p> : null}
    <header className="review-header">
      <div><p className="writing-review-kicker">{focused ? t("runner.writingFocused") : t("runner.writingReview")}</p><h1>{reviewData.review.test_title}</h1>{focusedUnitLabel(reviewData.review.attempt, t) ? <p>{focusedUnitLabel(reviewData.review.attempt, t)}</p> : null}</div>
      <p className="review-score"><span className="review-result-label">{focused ? t("runner.taskScore") : finalLabel}</span><b>{focused ? task.score ? task.score.overall.toFixed(2) : t("runner.notGraded") : reviewData.band_score === null ? t("runner.pending") : t("runner.band", { score: reviewData.band_score.toFixed(1) })}</b></p>
    </header>

    {!focused ? <section className="writing-assessment-summary" aria-label={t("runner.writingSummary")}>
      <div><p className="writing-review-kicker">{finalLabel}</p><h2>{reviewData.band_score === null ? t("runner.waitingCriteria") : t("runner.band", { score: reviewData.band_score.toFixed(1) })}</h2></div>
      <dl>
        <div><dt>{t("runner.task1Overall")}</dt><dd>{formatOverall(reviewData.task1_overall)}</dd></div>
        <div><dt>{t("runner.task2Overall")}</dt><dd>{formatOverall(reviewData.task2_overall)}</dd></div>
        <div><dt>{t("runner.weightedOverall")}</dt><dd>{formatOverall(reviewData.weighted_overall)}</dd></div>
        <div><dt>{t("runner.taskWeighting")}</dt><dd>{t("runner.taskWeights")}</dd></div>
      </dl>
    </section> : null}

    <div className="writing-assessment-grid">
      {reviewData.tasks.map((scoreTask) => {
        const selection = selections[scoreTask.writing_task_id];
        const complete = selection && Object.values(selection).every((value) => value !== "");
        const saving = savingTaskId === scoreTask.writing_task_id;
        return <section key={scoreTask.writing_task_id} className="writing-assessment-card" aria-label={t("runner.taskAssessment", { number: scoreTask.task_number })}>
          <div className="writing-assessment-card-heading"><div><p className="writing-review-kicker">{t("runner.writingTask", { number: scoreTask.task_number })}</p><h2>{t("runner.taskAssessment", { number: scoreTask.task_number })}</h2></div><strong>{scoreTask.score ? `${focused ? t("runner.taskScore") : t("runner.overall")} ${scoreTask.score.overall.toFixed(2)}` : focused ? t("runner.notGraded") : t("runner.awaitingScores")}</strong></div>
          <div className="writing-criteria-grid">
            {canEdit ? criteria.map(([key, abbreviation, fullName]) => <div key={key} className="writing-criterion-field"><label><span><b>{abbreviation}</b><small>{key === "ta" && scoreTask.task_number === 2 ? t("runner.taskResponse") : t(fullName)}</small></span><select disabled={!canEdit} aria-label={t("runner.taskCriterion", { number: scoreTask.task_number, criterion: abbreviation })} className="select-field" value={selection?.[key] ?? ""} onChange={(event) => updateCriterion(scoreTask.writing_task_id, key, event.target.value)}><option value="">{t("runner.notScored")}</option>{bands.map((band) => <option key={band} value={band}>{band}</option>)}</select></label><label className="field-label">{t("runner.criterionFeedback", { criterion: abbreviation })} <span className="font-normal text-[var(--muted)]">{t("runner.optional")}</span><textarea readOnly={!canEdit} aria-label={t("runner.taskCriterionFeedback", { number: scoreTask.task_number, criterion: abbreviation })} className="textarea-field mt-2" rows={3} maxLength={4000} value={feedback[scoreTask.writing_task_id]?.[key] ?? ""} onChange={(event) => updateFeedback(scoreTask.writing_task_id, key, event.target.value)} /></label></div>) : null}
            {!canEdit ? criteria.map(([key, abbreviation, fullName]) => <div key={key} className="writing-criterion-field"><p><b>{abbreviation}</b> · {key === "ta" && scoreTask.task_number === 2 ? t("runner.taskResponse") : t(fullName)}</p><p>{scoreTask.score?.[key]?.toFixed(1) ?? "—"}</p>{scoreTask.score?.[`${key}_feedback`] ? <p>{scoreTask.score[`${key}_feedback`]}</p> : null}</div>) : null}

          </div>
          {canEdit ? <button type="button" className="btn btn-writing" disabled={!complete || saving} onClick={() => void saveTaskScores(scoreTask.writing_task_id, scoreTask.task_number)}>{saving ? t("common.saving") : t("runner.saveTaskScores", { number: scoreTask.task_number })}</button> : null}
          {messages[scoreTask.writing_task_id] ? <p role="status" className="notice notice-success">{t(messages[scoreTask.writing_task_id]!.message, { number: messages[scoreTask.writing_task_id]!.number ?? "" })}</p> : null}
          {errors[scoreTask.writing_task_id] ? <p role="alert" className="notice notice-error">{t(errors[scoreTask.writing_task_id]!.message, { number: errors[scoreTask.writing_task_id]!.number ?? "" })}</p> : null}
        </section>;
      })}
    </div>

    {!focused || reviewData.tasks.length > 1 ? <div className="writing-task-tabs" role="tablist" aria-label={t("runner.writingReviewTasks")}>
      {reviewData.tasks.map((item, index) => <button key={item.writing_task_id} type="button" role="tab" aria-selected={index === taskIndex} className={index === taskIndex ? "active" : ""} onClick={() => setTaskIndex(index)}><b>{t("common.taskNumber", { number: item.task_number })}</b><span>{t("runner.wordCount", { count: item.word_count })}</span></button>)}
    </div> : null}
    <main className="writing-review-layout">
      <article className="writing-task-prompt"><p className="writing-task-kicker">{t("runner.writingTask", { number: task.task_number })}</p><h2>{t("common.taskNumber", { number: task.task_number })}</h2><p>{task.prompt}</p>{task.image_asset ? <Image unoptimized width={720} height={420} src={assetContentUrl(task.image_asset)} alt={t("runner.writingReference", { number: task.task_number })} /> : null}<div className="writing-task-guidance"><span>{t("runner.minimumWordsReview", { count: task.minimum_recommended_words ?? "—" })}</span><span>{t("runner.minutesSuggested", { minutes: task.recommended_duration_seconds ? Math.round(task.recommended_duration_seconds / 60) : "—" })}</span></div></article>
      <article className="writing-review-response" aria-label={t("runner.savedTaskResponse", { number: task.task_number })}>
        <header className="writing-review-response-heading">
          <div><p className="writing-response-kicker">{t("runner.savedResponse")}</p><h2>{t("runner.taskResponseHeading", { number: task.task_number })}</h2></div>
          <span className="writing-review-word-count">{t("runner.wordCount", { count: task.word_count })}</span>
        </header>
        <div className="writing-review-response-body">
          {task.content.trim() ? <AnnotatedEssay key={`${task.writing_task_id}:${currentEssayState?.runId ?? "none"}`} content={task.content} annotations={currentEssayState?.annotations} onViewFeedback={focusFeedback} /> : <p className="writing-review-response-empty">{t("runner.noSavedResponse")}</p>}
        </div>
      </article>
    </main>
    {!readOnly && !assignmentScope && (task.task_number === 1 || task.task_number === 2) ? <WritingAIAssessment key={task.writing_task_id} taskNumber={task.task_number} attemptId={reviewData.review.attempt.attempt_id} taskId={task.writing_task_id} hasEssay={Boolean(task.content.trim())} canCopy={canCopy} canSavePersonalFeedback={reviewData.grading?.context === "PERSONAL" && (user?.role === "USER" || user?.role === "TEACHER") && focused && !reviewData.review.attempt.test_session_id && reviewData.review.attempt.focused_unit?.kind === "WRITING_TASK" && reviewData.review.attempt.focused_unit.id === task.writing_task_id} essayContent={task.content} onAnnotationsChange={receiveAnnotations} onViewAnnotation={focusAnnotation} onCopy={(result) => copyAISuggestions(task.writing_task_id, result)} /> : null}
  </div>;
}

function formatOverall(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}
