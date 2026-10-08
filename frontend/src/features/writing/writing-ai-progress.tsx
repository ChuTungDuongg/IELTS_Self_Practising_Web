"use client";

import { useEffect, useState } from "react";
import { aiTraits, aiTraitNames, isActiveAIRun, type AIActivity, type AIWritingEvent, type AIWritingRun } from "@/lib/api/writing-ai";
import styles from "./writing-ai-assessment.module.css";

export const traitSubtitles = {
  ta: "Mức độ đáp ứng đề bài", cc: "Mạch lạc & liên kết", lr: "Từ vựng", gra: "Ngữ pháp",
};

export function activityFromEvent(event: AIWritingEvent): AIActivity | null {
  const phases: Partial<Record<AIWritingEvent["event_type"], AIActivity["phase"]>> = {
    "run.started": "preparing", "provider.starting": "starting_model", "provider.ready": "preparing",
    "criterion.started": "preparing", "evidence.request.started": "collecting_evidence",
    "evidence.validation.started": "validating_evidence", "criterion.evidence.completed": "evidence_collected",
    "criterion.scoring.started": "scoring", "criterion.scoring.validation.started": "validating_score",
    "criterion.retrying": "retrying", "criterion.completed": "completed", "criterion.failed": "failed", "run.failed": "failed", "run.completed": "completed",
  };
  const phase = phases[event.event_type];
  return phase ? { phase, criterion: event.payload.criterion ?? null, stage: event.payload.stage ?? null, started_at: event.created_at ?? new Date().toISOString() } : null;
}

function elapsedLabel(startedAt: string, now: number) {
  const start = Date.parse(startedAt);
  return Number.isFinite(start) ? `${Math.max(0, Math.floor((now - start) / 1000))} giây` : "";
}

function StageElapsed({ startedAt }: { startedAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  // Visible elapsed time is display-only; don't announce it every second.
  return <span className={styles.elapsed} aria-hidden="true">{elapsedLabel(startedAt, now)}</span>;
}

function phaseLabel(activity?: AIActivity | null) {
  switch (activity?.phase) {
    case "collecting_evidence": return "Đang thu thập dẫn chứng…";
    case "validating_evidence": return "Đang kiểm tra dẫn chứng…";
    case "evidence_collected": return "Đã thu thập dẫn chứng";
    case "scoring": return "Đang chấm điểm…";
    case "validating_score": return "Đang kiểm tra điểm và nhận xét…";
    case "retrying": return activity.stage === "scoring" ? "Đang sửa dữ liệu chấm điểm · thử lại 1 lần…" : "Đang sửa dữ liệu dẫn chứng · thử lại 1 lần…";
    default: return "Đang chuẩn bị…";
  }
}

export function ScoringProgress({ run }: { run: AIWritingRun | null }) {
  const active = isActiveAIRun(run);
  const count = aiTraits.filter((trait) => run?.progress[trait] || run?.result?.criteria[trait]).length;
  const activity = run?.activity;
  const failedTraits = new Set(aiTraits.filter((trait) => run?.failures?.[trait] && !run?.progress[trait] && !run?.result?.criteria[trait]));
  // Legacy failed rows contain progress but no persisted activity. Sequential
  // grading identifies the first unfinished criterion after completed results.
  const terminalTrait = run?.status === "FAILED" ? activity?.criterion
    ?? (failedTraits.size === 0 && (count > 0 || ["AI_PROVIDER_BAD_RESPONSE", "INVALID_PROVIDER_OUTPUT"].includes(run.error_code ?? ""))
      ? aiTraits.find((trait) => !run.progress[trait]) : null) : null;
  if (terminalTrait && !run?.progress[terminalTrait] && !run?.result?.criteria[terminalTrait]) failedTraits.add(terminalTrait);
  const failedCount = failedTraits.size;
  const activeCount = active && activity?.criterion && !run?.progress[activity.criterion] && !run?.failures?.[activity.criterion] ? 1 : 0;
  const summary = run?.status === "FAILED" ? "Chưa thể hoàn tất toàn bộ bài chấm."
    : run?.status === "COMPLETED" ? "Chấm bài hoàn tất"
    : activity?.phase === "starting_model" ? "Đang khởi động mô hình AI…"
    : active ? "Đang chấm bài…" : "Sẵn sàng chấm Task 2";

  return <section className={styles.trace} aria-label="Scoring Trace">
    <div className={styles.traceHeading}><h3>Scoring Trace · Tiến trình chấm</h3><span>{count} / 4 tiêu chí hoàn tất</span></div>
    {failedCount ? <p className={styles.progressCounts}>{count} hoàn tất · {failedCount} lỗi{activeCount ? ` · ${activeCount} đang chấm` : active ? ` · ${4 - count - failedCount} đang chờ` : ""}</p> : null}
    <p role="status" aria-live="polite">{summary}</p>
    <ol className={styles.timeline} aria-live="polite" aria-label="Tiến trình tiêu chí">
      {aiTraits.map((trait) => {
        const completed = run?.progress[trait] ?? run?.result?.criteria[trait];
        const failed = failedTraits.has(trait);
        const current = active && !completed && !failed && activity?.criterion === trait;
        const state = completed || run?.status === "COMPLETED" ? "COMPLETED" : failed ? "FAILED"
          : current ? activity?.phase === "retrying" ? "RETRYING" : "ACTIVE" : "WAITING";
        const evidenceCollected = completed || (activity?.criterion === trait && ["scoring", "validating_score", "evidence_collected"].includes(activity.phase))
          || (activity?.criterion === trait && activity.stage === "scoring");
        return <li key={trait} className={styles.step} data-state={state} aria-label={`Tiến trình ${aiTraitNames[trait]}`}>
          <span aria-hidden="true" className={`${styles.marker} ${current ? styles.activeMarker : ""}`}>{state === "COMPLETED" ? "✓" : state === "FAILED" ? "×" : state === "ACTIVE" || state === "RETRYING" ? "●" : "○"}</span>
          <div className={styles.stepBody}>
            <div className={styles.stepTitle}><strong>{aiTraitNames[trait]}</strong>{completed ? <b>Band {completed.score.toFixed(1)}</b> : null}</div>
            <small>{traitSubtitles[trait]}</small>
            {evidenceCollected ? <p>✓ Đã thu thập dẫn chứng</p> : null}
            <p>{state === "COMPLETED" ? "Đã chấm xong" : state === "FAILED" ? "Không thể hoàn tất tiêu chí này."
              : current ? phaseLabel(activity) : run?.status === "FAILED" ? "Chưa thực hiện" : "Đang chờ"}</p>
            {current && activity ? <StageElapsed startedAt={activity.started_at} /> : null}
          </div>
        </li>;
      })}
    </ol>
  </section>;
}
