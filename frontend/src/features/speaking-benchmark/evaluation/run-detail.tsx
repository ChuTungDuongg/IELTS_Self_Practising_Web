"use client";
import { useEffect, useState } from "react";
import * as api from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { ComparisonTable, criteria, bandText } from "./comparison-table";
import { CriterionFeedback } from "./criterion-feedback";
import styles from "../lab.module.css";

export function EvaluationRunDetail({ sampleId, run, labelRevision, onCancel, onRetry, onPlay }: { sampleId: string; run: api.GradingRun; labelRevision: number; onCancel: () => void; onRetry: (checkpoint: string, reason: string) => void; onPlay: (start: number, end: number) => void }) {
  const { t } = useTranslation();
  const [comparison, setComparison] = useState<api.Comparison | null>(null); const [label, setLabel] = useState(""); const [reason, setReason] = useState(""); const [error, setError] = useState("");
  useEffect(() => { let active = true; void api.runComparison(sampleId, run.id, label ? Number(label) : undefined).then(value => { if (active) { setComparison(value); setError(""); } }).catch(() => { if (active) setError("COMPARISON_UNAVAILABLE"); }); return () => { active = false; }; }, [sampleId, run.id, run.status, labelRevision, label]);
  return <div className={styles.stack}>
    <div role="status">{run.status} · {run.stage} · {run.progress}%</div>
    <p className={styles.muted}>{t("speakingEval.approved")} {run.review_revision} · {run.configuration.lexical_provider as string} · {run.config_fingerprint.slice(0, 12)}</p>
    {["PENDING", "RUNNING", "INTERRUPTED"].includes(run.status) && <button className="btn btn-secondary" onClick={onCancel}>{t("speakingEval.cancel")}</button>}
    {run.error_code && <p role="alert" className="notice">{run.error_code}</p>}
    {["INTERRUPTED", "CANCELLED"].includes(run.status) && run.requests.some(r => r.status === "INTERRUPTED_BILLING_UNKNOWN") && <div className="notice"><p>{t("speakingEval.unknown")}</p><label className={styles.field}>{t("speakingEval.reconcile")}<textarea className="textarea-field" value={reason} onChange={e => setReason(e.target.value)} minLength={10} maxLength={1000} /></label>{run.requests.filter(r => r.status === "INTERRUPTED_BILLING_UNKNOWN").map(r => <div key={r.id} className={styles.actions}><span>{r.stage} · {r.id.slice(0, 8)}</span><button className="btn btn-secondary" disabled={reason.trim().length < 10} onClick={() => onRetry(r.id, reason)}>{t("speakingEval.retry")}</button></div>)}</div>}
    {!run.prediction && run.checkpointed_scores && <p>{Object.entries(run.checkpointed_scores).map(([key, value]) => key.toUpperCase() + ": " + value.toFixed(1)).join(" · ")}</p>}
    {run.prediction && <><p className={styles.muted}>{t("speakingEval.advisory")}</p><div className={styles.actions}>{criteria.map(key => <span key={key}>{key.toUpperCase()} <strong>{bandText(run.prediction!.bands[key])}</strong></span>)}</div>{Object.entries(run.prediction.criteria).map(([key, value]) => <details key={key}><summary>{key.toUpperCase()} · {value.status} · {t("speakingEval.feedback")}</summary>{value.feedback && <CriterionFeedback value={value.feedback} onPlay={onPlay} />}</details>)}</>}
    <div className={styles.actions}><label>{t("speakingEval.labelRevision")}<input className="field" type="number" min={1} placeholder={t("speakingEval.latestLabel")} value={label} onChange={e => setLabel(e.target.value)} /></label><button className="btn btn-secondary" onClick={() => void api.runComparison(sampleId, run.id, label ? Number(label) : undefined).then(setComparison).catch(() => setError("COMPARISON_UNAVAILABLE"))}>{t("speakingEval.refreshComparison")}</button></div>
    {error && <p role="alert">{error}</p>}{comparison && <ComparisonTable value={comparison} />}
    <details><summary>{t("speakingEval.requests")} ({run.requests.filter(r => r.provider !== "cpu").length})</summary><ul>{run.requests.map(r => <li key={r.id}>{r.stage} · #{r.attempt} · {r.status} · {r.billing_state}<span className={styles.muted}> {JSON.stringify(r.usage)}</span></li>)}</ul></details>
  </div>;
}
