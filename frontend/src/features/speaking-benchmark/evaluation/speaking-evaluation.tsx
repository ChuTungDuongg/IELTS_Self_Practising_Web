"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import * as api from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { EvaluationRunDetail } from "./run-detail";
import styles from "../lab.module.css";

export function SpeakingEvaluation({ sampleId, labelRevision, onPlay }: { sampleId: string; labelRevision: number; onPlay: (start: number, end: number) => void }) {
  const { t } = useTranslation();
  const [available, setAvailable] = useState<api.GradingAvailability | null>(null);
  const [reviews, setReviews] = useState<{ revision: number; approved_at: string }[]>([]);
  const [revision, setRevision] = useState(""); const [provider, setProvider] = useState<api.LexicalProvider>("azure_pa");
  const [prepared, setPrepared] = useState<api.Preflight | null>(null);
  const [runs, setRuns] = useState<api.GradingRun[]>([]); const [selected, setSelected] = useState(""); const [offset, setOffset] = useState(0);
  const [costs, setCosts] = useState<Record<string, string>>({}); const [ceiling, setCeiling] = useState("");
  const [audioConsent, setAudioConsent] = useState(false); const [textConsent, setTextConsent] = useState(false); const [extraConsent, setExtraConsent] = useState(false);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [dialog, setDialog] = useState<{ checkpoint?: string; reason?: string } | null>(null);
  const submission = useRef<string | null>(null);
  const load = useCallback(async () => { const value = await api.listRuns(sampleId, offset); setRuns(value); setSelected(current => current || value[0]?.id || ""); }, [sampleId, offset]);
  useEffect(() => { let active = true; void Promise.all([api.gradingAvailability(), api.approvedReviews(sampleId)]).then(([status, history]) => { if (active) { setAvailable(status); setReviews(history); } }).catch(() => { if (active) setError("EVALUATION_UNAVAILABLE"); }); return () => { active = false; }; }, [sampleId]);
  useEffect(() => { let active = true; const refresh = () => { if (active) void load().catch(() => { if (active) setError("EVALUATION_HISTORY_UNAVAILABLE"); }); }; refresh(); const timer = setInterval(refresh, 3000); return () => { active = false; clearInterval(timer); }; }, [load]);
  const run = runs.find(r => r.id === selected); const chosen = available?.providers.find(p => p.provider === provider);
  const providers = ["azure_pa", "openai", ...(provider === "azure_pa" ? [] : [provider])];
  const validCosts = providers.every(p => Number.isFinite(Number(costs[p])) && Number(costs[p]) > 0) && Number(ceiling) > 0 && Number(ceiling) <= 1000 && providers.reduce((sum, p) => sum + Number(costs[p]), 0) <= Number(ceiling);
  const permitted = prepared?.can_queue && audioConsent && textConsent && (provider === "azure_pa" || extraConsent) && validCosts;
  function reset() { setPrepared(null); setAudioConsent(false); setTextConsent(false); setExtraConsent(false); submission.current = null; }
  function consent(): api.GradingConsent { return { azure_audio: true, llm_text: true, independent_provider: extraConsent, estimates_usd: Object.fromEntries(providers.map(p => [p, Number(costs[p])])), max_estimated_cost_usd: Number(ceiling) }; }
  async function action(callback: () => Promise<void>) { setBusy(true); setError(""); try { await callback(); } catch (failure) { setError(failure instanceof Error ? failure.message : "EVALUATION_FAILED"); } finally { setBusy(false); } }
  async function confirm() {
    if (!dialog || !permitted || !prepared) return;
    await action(async () => {
      const value = dialog.checkpoint && run ? await api.retryGrading(sampleId, run.id, dialog.checkpoint, dialog.reason!, consent()) : await api.submitGrading(sampleId, Number(revision), provider, prepared.preflight_fingerprint, submission.current ??= crypto.randomUUID(), consent());
      setSelected(value.id); setDialog(null); await load();
    });
  }
  return <section className={styles.panel} aria-label={t("speakingEval.title")}>
    <div className={styles.actions}><h2>{t("speakingEval.title")}</h2><Link href="/admin/speaking-benchmark/reports">{t("speakingEval.reports")}</Link></div>
    <p className={styles.muted}>{t("speakingEval.static")}</p>{error && <p role="alert" className="notice notice-error">{error}</p>}
    {available && chosen?.reasons.map(reason => <p className={styles.muted} key={reason}>{reason}</p>)}{!reviews.length && <p>{t("speakingEval.noApproved")}</p>}
    <div className={styles.fields}>
      <label className={styles.field}>{t("speakingEval.revision")}<select className="select-field" value={revision} onChange={e => { setRevision(e.target.value); reset(); }}><option value="">{t("speakingEval.choose")}</option>{reviews.map(r => <option key={r.revision} value={r.revision}>{r.revision} · {new Date(r.approved_at).toLocaleDateString()}</option>)}</select></label>
      <label className={styles.field}>{t("speakingEval.provider")}<select className="select-field" value={provider} onChange={e => { setProvider(e.target.value as api.LexicalProvider); reset(); }}>{api.lexicalProviders.map(p => <option key={p} value={p}>{p}</option>)}</select></label>
    </div>
    <button className="btn btn-secondary" disabled={busy || !revision || !chosen?.available} onClick={() => void action(async () => { setPrepared(await api.prepareGrading(sampleId, Number(revision), provider)); submission.current = null; })}>{t("speakingEval.preflight")}</button>
    {prepared && <div className={styles.stack}>
      <p>{t("speakingEval.candidate")}: {(prepared.candidate_ms / 1000).toFixed(1)} {t("speakingEval.seconds")} · {prepared.window_count} {t("speakingEval.windows")} · {t("speakingEval.parts")} {prepared.parts.join(", ")}</p>
      <div className={styles.actions}>{prepared.windows.map(w => <button key={w.id} className="btn btn-secondary" onClick={() => onPlay(w.start_ms, w.end_ms)}>{w.part_number} · {(w.start_ms / 1000).toFixed(1)}–{(w.end_ms / 1000).toFixed(1)} s</button>)}</div>
      <p className={styles.muted}>{t("speakingEval.maximum")}: {Object.entries(prepared.requests).map(([key, count]) => key + ": " + count).join(" · ")}</p>{prepared.warnings.map(w => <p className={styles.muted} key={w}>{w}</p>)}
      <div className={styles.fields}>{providers.map(p => <label key={p} className={styles.field}>{p} · {t("speakingEval.estimate")}<input className="field" inputMode="decimal" type="number" min="0.000001" step="any" value={costs[p] ?? ""} onChange={e => setCosts({ ...costs, [p]: e.target.value })} /></label>)}<label className={styles.field}>{t("speakingEval.ceiling")}<input className="field" type="number" min="0.000001" max="1000" step="any" value={ceiling} onChange={e => setCeiling(e.target.value)} /></label></div>
      <p className={styles.muted}>{t("speakingEval.costNote")}</p><div><label className={styles.check}><input type="checkbox" checked={audioConsent} onChange={e => setAudioConsent(e.target.checked)} />{t("speakingEval.azureConsent")}</label><label className={styles.check}><input type="checkbox" checked={textConsent} onChange={e => setTextConsent(e.target.checked)} />{t("speakingEval.llmConsent")}</label>{provider !== "azure_pa" && <label className={styles.check}><input type="checkbox" checked={extraConsent} onChange={e => setExtraConsent(e.target.checked)} />{t("speakingEval.extraConsent")}</label>}</div>
      <button className="btn btn-primary" disabled={busy || !permitted} onClick={() => setDialog({})}>{t("speakingEval.queue")}</button>
    </div>}
    <h3>{t("speakingEval.history")}</h3>{runs.length ? <><label className={styles.field}>{t("speakingEval.history")}<select className="select-field" value={selected} onChange={e => setSelected(e.target.value)}>{runs.map(r => <option value={r.id} key={r.id}>{new Date(r.created_at).toLocaleString()} · {r.status} · rev {r.review_revision}</option>)}</select></label>{run && <EvaluationRunDetail onPlay={onPlay} sampleId={sampleId} run={run} labelRevision={labelRevision} onCancel={() => void action(async () => { await api.cancelGrading(sampleId, run.id); await load(); })} onRetry={(checkpoint, reason) => { if (!permitted || Number(revision) !== run.review_revision || provider !== run.configuration.lexical_provider) { setError("RENEW_PREFLIGHT_AND_CONSENT_FOR_THIS_RUN"); return; } setDialog({ checkpoint, reason }); }} />}</> : <p className={styles.muted}>{t("speakingEval.empty")}</p>}
    <div className={styles.actions}><button className="btn btn-secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 25))}>{t("speakingEval.previous")}</button><button className="btn btn-secondary" disabled={runs.length < 25} onClick={() => setOffset(offset + 25)}>{t("speakingEval.next")}</button></div>
    <ConfirmDialog open={dialog !== null} title={t("speakingEval.confirm")} description={t("speakingEval.confirmText")} confirmLabel={t("speakingEval.queue")} pending={busy} errorMessage={error || undefined} onCancel={() => setDialog(null)} onConfirm={() => void confirm()} />
  </section>;
}

