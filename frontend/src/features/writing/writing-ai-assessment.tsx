"use client";

import { useEffect, useRef, useState } from "react";
import {
  aiTraits, traitNamesForTask, cancelAIWritingRun, createAIWritingRun, getAIWritingRun, isActiveAIRun, isCancelledAIRun, listAIWritingRuns,
  watchAIWritingRun, type AIWritingEvent, type AIWritingResult, type AIWritingRun,
} from "@/lib/api/writing-ai";
import { ApiError } from "@/lib/api/client";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ScoringProgress, activityFromEvent } from "./writing-ai-progress";
import { CriterionAssessmentCard } from "./writing-ai-criterion-card";
import styles from "./writing-ai-assessment.module.css";
import { Task1VisualStatus } from "./writing-ai-visual-details";

export function WritingAIAssessment({ attemptId, taskId, taskNumber = 2, hasEssay, canCopy, onCopy }: {
  attemptId: string; taskId: string; hasEssay: boolean; canCopy: boolean;
  taskNumber?: 1 | 2;
  onCopy: (result: AIWritingResult) => void;
}) {
  const [runs, setRuns] = useState<AIWritingRun[]>([]);
  const [run, setRun] = useState<AIWritingRun | null>(null);
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

  useEffect(() => {
    let disposed = false;
    listAIWritingRuns(attemptId, taskId).then((saved) => {
      if (disposed) return;
      setConfigured(saved.configured);
      setRuns(saved.items);
      setRun(saved.items.find(isActiveAIRun) ?? saved.items[0] ?? null);
    }).catch(() => { if (!disposed) setError("Không thể tải các bài chấm AI đã lưu. Bạn có thể thử chấm lại."); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [attemptId, taskId]);

  useEffect(() => {
    if (!runId || !observing) return;
    let disposed = false;
    const stopObserving = watchAIWritingRun(runId, {
      event(event: AIWritingEvent) {
        if (disposed) return;
        const activity = activityFromEvent(event);
        const trait = event.payload.criterion;
        setRun((current) => current?.id === runId ? {
          ...current,
          error_code: event.event_type === "run.failed" ? event.payload.error_code ?? current.error_code : current.error_code,
          activity: activity ? { ...activity, criterion: event.event_type === "run.failed" ? activity.criterion ?? current.activity?.criterion ?? null : activity.criterion } : current.activity,
          progress: trait && event.payload.result ? { ...current.progress, [trait]: event.payload.result } : current.progress,
          task1_analysis: event.payload.task1_analysis ?? current.task1_analysis,
          failures: trait && event.event_type === "criterion.failed" ? { ...current.failures, [trait]: {
            error_code: event.payload.error_code ?? "AI_GRADING_FAILED",
            error_message: "Không thể hoàn tất tiêu chí này.", stage: event.payload.stage,
          } } : current.failures,
        } : current);
        // Terminal UI overrides transient phases immediately. Keep observation
        // alive until JSON reconciliation finishes, including during an outage.
        if (event.event_type === "run.failed") { setTerminal("FAILED"); setError(event.payload.error_code === "AI_GRADING_CANCELLED" ? "" : aiErrorMessage(event.payload.error_code)); }
        if (event.event_type === "run.completed") setTerminal("COMPLETED");
      },
      snapshot(saved) {
        if (disposed || saved.id !== runId) return;
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
      {run?.result && canCopy ? <button type="button" className="btn" disabled={active || starting || stopping} onClick={() => { onCopy(run.result!); setNotice(`Đã chép gợi ý AI. Bạn có thể chỉnh sửa; cần bấm Save Task ${taskNumber} scores để lưu điểm chính thức.`); }}>Chép gợi ý AI vào biểu mẫu</button> : null}
    </div>
    <ConfirmDialog open={confirmStop && active} title="Dừng chấm AI?" description="Quá trình chấm hiện tại sẽ dừng. Các tiêu chí đã hoàn tất vẫn được giữ lại. Điểm chính thức của bài Writing không bị thay đổi." confirmLabel="Dừng chấm" cancelLabel="Tiếp tục chấm" pendingLabel="Đang dừng…" pending={stopping} errorMessage={stopError} onCancel={() => setConfirmStop(false)} onConfirm={() => void stop()} />
    {notice ? <p role="status">{notice}</p> : null}
    {cancelled ? <p role="status">Đã dừng chấm AI. Các tiêu chí hoàn tất trước đó vẫn được giữ lại.</p> : null}
    {error || (visibleRun?.status === "FAILED" && !cancelled) ? <p role="alert" className="notice notice-error">{visibleRun?.status === "FAILED" && !cancelled ? aiErrorMessage(visibleRun.error_code) : error}</p> : null}
    <ScoringProgress run={visibleRun} taskNumber={taskNumber} />
    {taskNumber === 1 && visualAnalysis ? <Task1VisualStatus analysis={visualAnalysis} /> : null}
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
    <div className={styles.criteria}>{aiTraits.map((trait) => {
      const assessment = run?.result?.criteria[trait] ?? run?.progress[trait];
      return assessment ? <CriterionAssessmentCard key={trait} trait={trait} assessment={assessment} taskNumber={taskNumber} visualAnalysis={visualAnalysis} /> : null;
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
