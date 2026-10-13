"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  aiTraits, traitNamesForTask, cancelAIWritingRun, createAIWritingRun, getAIWritingRun, isActiveAIRun, isCancelledAIRun, listAIWritingRuns,
  watchAIWritingRun, type AIWritingEvent, type AIWritingResult, type AIWritingRun,
  getAIPracticeFeedback, saveAIPracticeFeedback, type AIPracticeFeedback,
  type AITrait, type WritingAnnotation,
} from "@/lib/api/writing-ai";
import { ApiError } from "@/lib/api/client";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ScoringProgress, activityFromEvent } from "./writing-ai-progress";
import { CriterionAssessmentCard } from "./writing-ai-criterion-card";
import styles from "./writing-ai-assessment.module.css";
import { Task1VisualStatus } from "./writing-ai-visual-details";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { SavedAIPracticeFeedback, WritingRelevanceNotice } from "./writing-ai-practice-feedback";
import { AnnotationDetails, validEssayAnnotations } from "./annotated-essay";

export type EssayAnnotationState = { runId: string | null; annotations: WritingAnnotation[] };
type LiveFeedback = { runId: string; annotations: Partial<Record<AITrait, WritingAnnotation[]>>; phases: Partial<Record<AITrait, "generating" | "completed">> };

function reconcileFeedbackSnapshot(saved: AIWritingRun, previous: LiveFeedback | null): LiveFeedback | null {
  if (!isActiveAIRun(saved)) return null;
  const current = previous?.runId === saved.id ? previous : { runId: saved.id, annotations: {}, phases: {} };
  const annotations = { ...current.annotations }, phases = { ...current.phases };
  for (const trait of aiTraits) {
    const assessment = saved.result?.criteria[trait] ?? saved.progress[trait];
    if (saved.failures?.[trait] || (assessment && assessment.feedback_status !== "PENDING")) {
      annotations[trait] = []; phases[trait] = "completed";
    } else if (assessment?.feedback_status === "PENDING") phases[trait] = "generating";
  }
  return { runId: saved.id, annotations, phases };
}

export function WritingAIAssessment({ attemptId, taskId, taskNumber = 2, hasEssay, canCopy, canSavePersonalFeedback = false, onCopy, essayContent, onAnnotationsChange, onViewAnnotation }: {
  attemptId: string; taskId: string; hasEssay: boolean; canCopy: boolean;
  taskNumber?: 1 | 2;
  canSavePersonalFeedback?: boolean;
  onCopy: (result: AIWritingResult) => void;
  essayContent?: string;
  onAnnotationsChange?: (state: EssayAnnotationState) => void;
  onViewAnnotation?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [personalFeedback, setPersonalFeedback] = useState<AIPracticeFeedback | null>(null);
  const [feedbackLoading, setFeedbackLoading] = useState(true);
  const [feedbackSaving, setFeedbackSaving] = useState(false);
  const [feedbackLoadError, setFeedbackLoadError] = useState(false);
  const [feedbackSaveError, setFeedbackSaveError] = useState(false);
  const [runs, setRuns] = useState<AIWritingRun[]>([]);
  const [run, setRun] = useState<AIWritingRun | null>(null);
  const [liveFeedback, setLiveFeedback] = useState<LiveFeedback | null>(null);
  const [terminal, setTerminal] = useState<"FAILED" | "COMPLETED" | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const stopInFlight = useRef(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [stopError, setStopError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const runId = run?.id;
  const observing = isActiveAIRun(run);
  const visibleRun = run && terminal ? { ...run, status: terminal } : run;
  const active = isActiveAIRun(visibleRun);
  const cancelled = isCancelledAIRun(visibleRun);
  const aiTraitNames = traitNamesForTask(taskNumber);
  const visualAnalysis = run?.task1_analysis ?? (run?.result?.task_number === 1 ? run.result.task1_analysis : null);
  const annotations = useMemo(() => {
    if (!run || terminal === "FAILED" || run.status === "FAILED") return [];
    const combined = aiTraits.flatMap(trait => run.result
      ? run.result.criteria[trait].annotations ?? []
      : [...(run.progress[trait]?.annotations ?? []), ...(liveFeedback?.runId === run.id ? liveFeedback.annotations[trait] ?? [] : [])]);
    const unique = [...new Map(combined.map(annotation => [annotation.id, annotation])).values()];
    return essayContent === undefined ? unique.filter(annotation => (annotation.criterion === "gra" || annotation.criterion === "lr") && (annotation.kind !== "ERROR" || annotation.confidence === "HIGH")) : validEssayAnnotations(essayContent, unique);
  }, [run, terminal, liveFeedback, essayContent]);
  const feedbackPhases = liveFeedback && liveFeedback.runId === runId ? liveFeedback.phases : undefined;

  useEffect(() => { onAnnotationsChange?.({ runId: runId ?? null, annotations }); }, [runId, annotations, onAnnotationsChange]);

  useEffect(() => {
    if (!canSavePersonalFeedback) return;
    let disposed = false;
    getAIPracticeFeedback(attemptId, taskId).then(saved => { if (!disposed) setPersonalFeedback(saved); })
      .catch(() => { if (!disposed) setFeedbackLoadError(true); })
      .finally(() => { if (!disposed) setFeedbackLoading(false); });
    return () => { disposed = true; };
  }, [attemptId, taskId, canSavePersonalFeedback]);

  async function savePersonalFeedback() {
    if (!canSavePersonalFeedback || run?.status !== "COMPLETED" || !run.result || feedbackSaving) return;
    setFeedbackSaving(true); setFeedbackSaveError(false);
    try {
      setPersonalFeedback(await saveAIPracticeFeedback(attemptId, taskId, run.id));
      setFeedbackLoadError(false);
    } catch { setFeedbackSaveError(true); }
    finally { setFeedbackSaving(false); }
  }

  useEffect(() => {
    let disposed = false;
    listAIWritingRuns(attemptId, taskId).then((saved) => {
      if (disposed) return;
      setConfigured(saved.configured);
      setRuns(saved.items);
      const selected = saved.items.find(isActiveAIRun) ?? saved.items[0] ?? null;
      setRun(selected);
      setLiveFeedback(selected ? reconcileFeedbackSnapshot(selected, null) : null);
    }).catch(() => { if (!disposed) setError("Không thể tải các bài chấm AI đã lưu. Bạn có thể thử chấm lại."); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [attemptId, taskId]);

  useEffect(() => {
    if (!runId || !observing) return;
    let disposed = false;
    let sequence = 0;
    const stopObserving = watchAIWritingRun(runId, {
      event(event: AIWritingEvent) {
        if (disposed || event.sequence <= sequence) return;
        sequence = event.sequence;
        const activity = activityFromEvent(event);
        const trait = event.payload.criterion;
        const annotation = event.payload.annotation;
        if (event.event_type.startsWith("criterion.feedback.") || event.event_type === "criterion.completed" || event.event_type === "criterion.failed") {
          setLiveFeedback(previous => {
            const current = previous?.runId === runId ? previous : { runId, annotations: {}, phases: {} };
            if (!trait) return current;
            if (current.phases[trait] === "completed" && (event.event_type === "criterion.feedback.started" || event.event_type === "criterion.feedback.annotation")) return current;
            if (event.event_type === "criterion.feedback.annotation" && annotation?.criterion === trait) {
              const items = current.annotations[trait] ?? [];
              return items.some(item => item.id === annotation.id) || items.length >= 4 ? current
                : { ...current, annotations: { ...current.annotations, [trait]: [...items, annotation] } };
            }
            if (event.event_type === "criterion.feedback.started") return { ...current, annotations: { ...current.annotations, [trait]: [] }, phases: { ...current.phases, [trait]: "generating" } };
            if (event.event_type === "criterion.feedback.completed" || event.event_type === "criterion.completed" || event.event_type === "criterion.failed") {
              return { ...current, annotations: { ...current.annotations, [trait]: [] }, phases: { ...current.phases, [trait]: "completed" } };
            }
            return current;
          });
        }
        setRun((current) => {
          if (current?.id !== runId) return current;
          // A replayed generation checkpoint cannot supersede persisted feedback.
          const finalized = trait && current.progress[trait] && current.progress[trait]?.feedback_status !== "PENDING";
          if (finalized && event.event_type === "criterion.feedback.started") return current;
          return {
          ...current,
          error_code: event.event_type === "run.failed" ? event.payload.error_code ?? current.error_code : current.error_code,
          activity: activity ? { ...activity, criterion: event.event_type === "run.failed" ? activity.criterion ?? current.activity?.criterion ?? null : activity.criterion } : current.activity,
          progress: trait && event.payload.result ? { ...current.progress, [trait]: event.payload.result } : current.progress,
          task1_analysis: event.payload.task1_analysis ?? current.task1_analysis,
          relevance: event.payload.relevance ?? current.relevance,
          failures: trait && event.event_type === "criterion.failed" ? { ...current.failures, [trait]: {
            error_code: event.payload.error_code ?? "AI_GRADING_FAILED",
            error_message: "Không thể hoàn tất tiêu chí này.", stage: event.payload.stage,
          } } : current.failures,
          };
        });
        // Terminal UI overrides transient phases immediately. Keep observation
        // alive until JSON reconciliation finishes, including during an outage.
        if (event.event_type === "run.failed") { setLiveFeedback(null); setTerminal("FAILED"); setError(event.payload.error_code === "AI_GRADING_CANCELLED" ? "" : aiErrorMessage(event.payload.error_code)); }
        if (event.event_type === "run.completed") setTerminal("COMPLETED");
      },
      snapshot(saved) {
        if (disposed || saved.id !== runId) return;
        setLiveFeedback(previous => reconcileFeedbackSnapshot(saved, previous));
        setRun((current) => current?.id === saved.id && !(isCancelledAIRun(current) && isActiveAIRun(saved)) ? { ...saved, progress: { ...current.progress, ...saved.progress }, failures: { ...current.failures, ...saved.failures }, activity: saved.activity ?? current.activity } : current);
        setTerminal(null);
        setError("");
        setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      },
      error(message) { if (!disposed) setError(message); },
    });
    // Task tabs remount this view. Stop observing; only the Stop button cancels grading.
    return () => { disposed = true; stopObserving(); };
  }, [runId, observing]);

  async function grade(force: boolean) {
    if (starting || stopping || active) return;
    setStarting(true); setError(""); setNotice(""); setConfirmStop(false);
    try {
      const created = await createAIWritingRun(attemptId, taskId, force);
      const saved = await getAIWritingRun(created.run_id);
      setRun(saved);
      setLiveFeedback(reconcileFeedbackSnapshot(saved, null));
      setTerminal(null);
      setConfigured(true);
      setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      if (created.cache_hit) setNotice("Đã khôi phục bài chấm AI đã lưu cho câu trả lời này.");
    } catch (failure) {
      setError(failure instanceof ApiError ? aiErrorMessage(failure.code) : "Không thể bắt đầu chấm AI. Vui lòng thử lại.");
      if (failure instanceof ApiError && failure.code === "AI_NOT_CONFIGURED") setConfigured(false);
    } finally { setStarting(false); }
  }

  async function stop() {
    if (!runId || !active || stopInFlight.current) return;
    stopInFlight.current = true;
    setStopping(true); setStopError("");
    try {
      const saved = await cancelAIWritingRun(runId);
      setRun((current) => current?.id === saved.id ? { ...saved, progress: { ...current.progress, ...saved.progress } } : current);
      setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      setTerminal(null); setError(""); setConfirmStop(false);
      if (saved.status === "COMPLETED") setNotice("Bài chấm AI đã hoàn tất trước khi yêu cầu dừng được xử lý.");
    } catch {
      setStopError("Chưa thể dừng chấm AI. Vui lòng thử lại.");
    } finally { stopInFlight.current = false; setStopping(false); }
  }

  return <section className={styles.panel} aria-label="AI Assessment">
    <div className={styles.heading}><div><p className="writing-review-kicker">AI Assessment</p><h2>Đánh giá AI · Task {taskNumber}</h2></div><span className={styles.badge}>Ý kiến tham khảo</span></div>
    <p>AI chỉ đóng vai trò tham khảo. Điểm chính thức chỉ thay đổi khi người chấm chủ động lưu.</p>
    {configured === false ? <p role="status">Chấm AI chưa được cấu hình.</p> : null}
    {!hasEssay ? <p>Cần có câu trả lời Task {taskNumber} đã lưu để chấm AI.</p> : null}
    {run?.prompt_version === "mts-task2-v1" ? <p className={styles.legacy}>Bản chấm cũ · trước khi chuyển nhận xét sang tiếng Việt</p> : null}
    <div className={styles.actions}>
      <button type="button" className="btn btn-writing" disabled={loading || starting || stopping || active || !hasEssay || configured === false} onClick={() => void grade(Boolean(run))}>
        {starting ? "Đang bắt đầu chấm AI…" : active ? "Đang chấm với AI…" : run ? "Chấm lại với AI" : `Chấm Task ${taskNumber} với AI`}
      </button>
      {active ? <button type="button" className="btn btn-secondary" disabled={stopping} onClick={() => { setStopError(""); setConfirmStop(true); }}>{stopping ? "Đang dừng…" : "Dừng chấm"}</button> : null}
      {run?.status === "COMPLETED" && run.result && canCopy ? <button type="button" className="btn" disabled={active || starting || stopping} onClick={() => { onCopy(run.result!); setNotice(`Đã chép gợi ý AI. Bạn có thể chỉnh sửa; cần bấm Save Task ${taskNumber} scores để lưu điểm chính thức.`); }}>Chép gợi ý AI vào biểu mẫu</button> : null}
      {canSavePersonalFeedback && run?.status === "COMPLETED" && run.result ? <button type="button" className="btn" disabled={active || starting || stopping || feedbackLoading || feedbackSaving || personalFeedback?.source_run_id === run.id} onClick={() => void savePersonalFeedback()}>
        {t(feedbackSaving ? "writingAI.savingFeedback" : personalFeedback?.source_run_id === run.id ? "writingAI.feedbackSaved" : personalFeedback ? "writingAI.updateFeedback" : "writingAI.saveFeedback")}
      </button> : null}
    </div>
    <ConfirmDialog open={confirmStop && active} title="Dừng chấm AI?" description="Quá trình chấm hiện tại sẽ dừng. Các tiêu chí đã hoàn tất vẫn được giữ lại. Điểm chính thức của bài Writing không bị thay đổi." confirmLabel="Dừng chấm" cancelLabel="Tiếp tục chấm" pendingLabel="Đang dừng…" pending={stopping} errorMessage={stopError} onCancel={() => setConfirmStop(false)} onConfirm={() => void stop()} />
    {notice ? <p role="status">{notice}</p> : null}
    {cancelled ? <p role="status">Đã dừng chấm AI. Các tiêu chí hoàn tất trước đó vẫn được giữ lại.</p> : null}
    {error || (visibleRun?.status === "FAILED" && !cancelled) ? <p role="alert" className="notice notice-error">{visibleRun?.status === "FAILED" && !cancelled ? aiErrorMessage(visibleRun.error_code) : error}</p> : null}
    <ScoringProgress run={visibleRun} taskNumber={taskNumber} feedbackPhases={feedbackPhases} annotationCount={annotations.length} />
    {taskNumber === 1 && visualAnalysis ? <Task1VisualStatus analysis={visualAnalysis} /> : null}
    <WritingRelevanceNotice relevance={run?.result?.relevance ?? run?.relevance} />
    {canSavePersonalFeedback && feedbackLoadError ? <p role="alert">{t("writingAI.loadFeedbackError")}</p> : null}
    {canSavePersonalFeedback && feedbackSaveError ? <p role="alert">{t("writingAI.saveFeedbackError")}</p> : null}
    {canSavePersonalFeedback && personalFeedback ? <SavedAIPracticeFeedback feedback={personalFeedback} taskNumber={taskNumber} /> : null}
    {run?.result ? <section className={styles.overall} aria-label={`AI Task ${taskNumber} overall summary`}>
      <header className={styles.overallHeading}>
        <div className={styles.overallCopy}>
          <p className={styles.overallEyebrow}>AI Task {taskNumber} · Ý kiến tham khảo</p>
          <h3>Điểm tổng hợp AI</h3>
          <p className={styles.overallSupport}>Trung bình đều của 4 tiêu chí Task {taskNumber}. Không phải band Writing chính thức.</p>
        </div>
        <strong className={styles.overallBand}>Band <span>{run.result.overall_band.toFixed(1)}</span></strong>
      </header>
      <dl className={styles.overallCriteria}>
        {aiTraits.map((trait) => <div key={trait}>
          <dt><abbr title={aiTraitNames[trait]}>{trait === "ta" ? taskNumber === 1 ? "TA" : "TR" : trait.toUpperCase()}</abbr><span>{aiTraitNames[trait]}</span></dt>
          <dd>{run.result!.criteria[trait].score.toFixed(1)}</dd>
        </div>)}
      </dl>
    </section> : null}
    {annotations.length || run?.status === "COMPLETED" ? <section className={styles.trace} aria-label={t("writingAI.feedbackTitle")}>
      <h3>{t("writingAI.feedbackTitle")}</h3>
      {annotations.length ? <ul className={styles.annotations}>{annotations.map(annotation => <li key={annotation.id} tabIndex={-1} data-feedback-annotation-id={annotation.id}>
        <AnnotationDetails annotation={annotation} />
        {onViewAnnotation ? <button type="button" className="btn btn-secondary" onClick={() => onViewAnnotation(annotation.id)}>{t("writingAI.viewInEssay")}</button> : null}
      </li>)}</ul> : <p>{t(run?.result && ["gra", "lr"].some(trait => run.result!.criteria[trait as "gra" | "lr"].feedback_status === "UNAVAILABLE") ? "writingAI.feedbackUnavailable" : "writingAI.noLanguageIssues")}</p>}
    </section> : null}
    <div className={styles.criteria}>{aiTraits.map((trait) => {
      const assessment = run?.result?.criteria[trait] ?? run?.progress[trait];
      return assessment ? <CriterionAssessmentCard key={trait} trait={trait} assessment={assessment} taskNumber={taskNumber} visualAnalysis={visualAnalysis} generatingFeedback={active && feedbackPhases?.[trait] === "generating"} feedbackFailed={!run?.result?.criteria[trait] && (Boolean(run?.failures?.[trait]) || (visibleRun?.status === "FAILED" && assessment.feedback_status === "PENDING"))} /> : null;
    })}</div>
    {runs.some((item) => item.status === "COMPLETED" && item.id !== run?.id) ? <details className={styles.history}><summary>Các bài chấm AI trước</summary><ul>{runs.filter((item) => item.status === "COMPLETED").map((item) => <li key={item.id}><button type="button" className="btn" disabled={active || starting || stopping} onClick={() => { setRun(item); setTerminal(null); setError(""); setNotice(""); }}>{new Date(item.created_at).toLocaleString("vi-VN")} · {item.result?.overall_band.toFixed(1)} · {item.prompt_version}</button></li>)}</ul></details> : null}
  </section>;
}

function aiErrorMessage(code?: string | null) {
  if (["AI_TASK1_IMAGE_MISSING", "AI_TASK1_IMAGE_INVALID"].includes(code ?? "")) return "Task 1 cần có hình hợp lệ trong phiên bản bài thi đã làm để chấm AI.";
  if (["AI_PROVIDER_BAD_RESPONSE", "INVALID_PROVIDER_OUTPUT"].includes(code ?? "")) return "Một số tiêu chí chưa thể chấm xong do dữ liệu chưa hợp lệ. Các kết quả đã hoàn tất được giữ lại; bạn có thể thử chấm lại.";
  if (code === "AI_NOT_CONFIGURED") return "Chấm AI chưa được cấu hình.";
  if (["AI_PROVIDER_TIMEOUT", "AI_PROVIDER_STARTUP_TIMEOUT", "PROVIDER_TIMEOUT"].includes(code ?? "")) return "AI chưa hoàn tất trong thời gian cho phép. Các phần đã chấm được giữ lại; bạn có thể chấm lại.";
  if (["AI_PROVIDER_AUTH_FAILED", "AI_PROVIDER_ENDPOINT_ERROR", "AI_MODEL_UNAVAILABLE"].includes(code ?? "")) return "Dịch vụ AI chưa sẵn sàng. Vui lòng kiểm tra cấu hình backend; các phần đã chấm vẫn được giữ lại.";
  return "AI chưa thể hoàn tất toàn bộ bài chấm. Các tiêu chí đã hoàn thành vẫn được giữ lại. Bạn có thể bấm Chấm lại với AI.";
}
