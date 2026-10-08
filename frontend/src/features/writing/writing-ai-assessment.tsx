"use client";

import { useEffect, useState } from "react";
import {
  aiTraits, aiTraitNames, createAIWritingRun, getAIWritingRun, isActiveAIRun, listAIWritingRuns,
  watchAIWritingRun, type AIWritingEvent, type AIWritingResult, type AIWritingRun,
} from "@/lib/api/writing-ai";
import { ApiError } from "@/lib/api/client";
import { ScoringProgress, activityFromEvent } from "./writing-ai-progress";
import { CriterionAssessmentCard } from "./writing-ai-criterion-card";
import styles from "./writing-ai-assessment.module.css";

export function WritingAIAssessment({ attemptId, taskId, hasEssay, canCopy, onCopy }: {
  attemptId: string; taskId: string; hasEssay: boolean; canCopy: boolean;
  onCopy: (result: AIWritingResult) => void;
}) {
  const [runs, setRuns] = useState<AIWritingRun[]>([]);
  const [run, setRun] = useState<AIWritingRun | null>(null);
  const [terminal, setTerminal] = useState<"FAILED" | "COMPLETED" | null>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const runId = run?.id;
  const observing = isActiveAIRun(run);
  const visibleRun = run && terminal ? { ...run, status: terminal } : run;
  const active = isActiveAIRun(visibleRun);

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
    return watchAIWritingRun(runId, {
      event(event: AIWritingEvent) {
        const activity = activityFromEvent(event);
        const trait = event.payload.criterion;
        setRun((current) => current?.id === runId ? {
          ...current,
          error_code: event.event_type === "run.failed" ? event.payload.error_code ?? current.error_code : current.error_code,
          activity: activity ? { ...activity, criterion: event.event_type === "run.failed" ? activity.criterion ?? current.activity?.criterion ?? null : activity.criterion } : current.activity,
          progress: trait && event.payload.result ? { ...current.progress, [trait]: event.payload.result } : current.progress,
          failures: trait && event.event_type === "criterion.failed" ? { ...current.failures, [trait]: {
            error_code: event.payload.error_code ?? "AI_GRADING_FAILED",
            error_message: "Không thể hoàn tất tiêu chí này.", stage: event.payload.stage,
          } } : current.failures,
        } : current);
        // Terminal UI overrides transient phases immediately. Keep observation
        // alive until JSON reconciliation finishes, including during an outage.
        if (event.event_type === "run.failed") { setTerminal("FAILED"); setError(aiErrorMessage(event.payload.error_code)); }
        if (event.event_type === "run.completed") setTerminal("COMPLETED");
      },
      snapshot(saved) {
        setRun((current) => current?.id === saved.id ? { ...saved, progress: { ...current.progress, ...saved.progress }, failures: { ...current.failures, ...saved.failures }, activity: saved.activity ?? current.activity } : current);
        setTerminal(null);
        setError("");
        setRuns((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      },
      error: setError,
    });
  }, [runId, observing]);

  async function grade(force: boolean) {
    if (starting || active) return;
    setStarting(true); setError(""); setNotice("");
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

  return <section className={styles.panel} aria-label="AI Assessment">
    <div className={styles.heading}><div><p className="writing-review-kicker">AI Assessment</p><h2>Đánh giá AI · Task 2</h2></div><span className={styles.badge}>Ý kiến tham khảo</span></div>
    <p>AI chỉ đóng vai trò tham khảo. Điểm chính thức chỉ thay đổi khi người chấm chủ động lưu.</p>
    {configured === false ? <p role="status">Chấm AI chưa được cấu hình.</p> : null}
    {!hasEssay ? <p>Cần có câu trả lời Task 2 đã lưu để chấm AI.</p> : null}
    {run?.prompt_version === "mts-task2-v1" ? <p className={styles.legacy}>Bản chấm cũ · trước khi chuyển nhận xét sang tiếng Việt</p> : null}
    <div className={styles.actions}>
      <button type="button" className="btn btn-writing" disabled={loading || starting || active || !hasEssay || configured === false} onClick={() => void grade(Boolean(run))}>
        {starting ? "Đang bắt đầu chấm AI…" : active ? "Đang chấm với AI…" : run ? "Chấm lại với AI" : "Chấm Task 2 với AI"}
      </button>
      {run?.result && canCopy ? <button type="button" className="btn" disabled={active || starting} onClick={() => { onCopy(run.result!); setNotice("Đã chép gợi ý AI. Bạn có thể chỉnh sửa; cần bấm Save Task 2 scores để lưu điểm chính thức."); }}>Chép gợi ý AI vào biểu mẫu</button> : null}
    </div>
    {notice ? <p role="status">{notice}</p> : null}
    {error || visibleRun?.status === "FAILED" ? <p role="alert" className="notice notice-error">{visibleRun?.status === "FAILED" ? aiErrorMessage(visibleRun.error_code) : error}</p> : null}
    <ScoringProgress run={visibleRun} />
    {run?.result ? <section className={styles.overall} aria-label="AI Task 2 overall summary">
      <header className={styles.overallHeading}>
        <div className={styles.overallCopy}>
          <p className={styles.overallEyebrow}>AI Task 2 · Ý kiến tham khảo</p>
          <h3>Điểm tổng hợp AI</h3>
          <p className={styles.overallSupport}>Trung bình đều của 4 tiêu chí Task 2. Không phải band Writing chính thức.</p>
        </div>
        <strong className={styles.overallBand}>Band <span>{run.result.overall_band.toFixed(1)}</span></strong>
      </header>
      <dl className={styles.overallCriteria}>
        {aiTraits.map((trait) => <div key={trait}>
          <dt><abbr title={aiTraitNames[trait]}>{trait === "ta" ? "TR" : trait.toUpperCase()}</abbr><span>{aiTraitNames[trait]}</span></dt>
          <dd>{run.result!.criteria[trait].score.toFixed(1)}</dd>
        </div>)}
      </dl>
    </section> : null}
    <div className={styles.criteria}>{aiTraits.map((trait) => {
      const assessment = run?.result?.criteria[trait] ?? run?.progress[trait];
      return assessment ? <CriterionAssessmentCard key={trait} trait={trait} assessment={assessment} /> : null;
    })}</div>
    {runs.some((item) => item.status === "COMPLETED" && item.id !== run?.id) ? <details className={styles.history}><summary>Các bài chấm AI trước</summary><ul>{runs.filter((item) => item.status === "COMPLETED").map((item) => <li key={item.id}><button type="button" className="btn" disabled={active || starting} onClick={() => { setRun(item); setTerminal(null); setError(""); setNotice(""); }}>{new Date(item.created_at).toLocaleString("vi-VN")} · {item.result?.overall_band.toFixed(1)} · {item.prompt_version}</button></li>)}</ul></details> : null}
  </section>;
}

function aiErrorMessage(code?: string | null) {
  if (["AI_PROVIDER_BAD_RESPONSE", "INVALID_PROVIDER_OUTPUT"].includes(code ?? "")) return "Một số tiêu chí chưa thể chấm xong do dữ liệu chưa hợp lệ. Các kết quả đã hoàn tất được giữ lại; bạn có thể thử chấm lại.";
  if (code === "AI_NOT_CONFIGURED") return "Chấm AI chưa được cấu hình.";
  if (["AI_PROVIDER_TIMEOUT", "AI_PROVIDER_STARTUP_TIMEOUT", "PROVIDER_TIMEOUT"].includes(code ?? "")) return "AI chưa hoàn tất trong thời gian cho phép. Các phần đã chấm được giữ lại; bạn có thể chấm lại.";
  if (["AI_PROVIDER_AUTH_FAILED", "AI_PROVIDER_ENDPOINT_ERROR", "AI_MODEL_UNAVAILABLE"].includes(code ?? "")) return "Dịch vụ AI chưa sẵn sàng. Vui lòng kiểm tra cấu hình backend; các phần đã chấm vẫn được giữ lại.";
  return "AI chưa thể hoàn tất toàn bộ bài chấm. Các tiêu chí đã hoàn thành vẫn được giữ lại. Bạn có thể bấm Chấm lại với AI.";
}
