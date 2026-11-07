"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationKey } from "@/lib/i18n/types";
import { criteria } from "./comparison-table";
import { ReportCharts } from "./report-charts";
import lab from "../lab.module.css";
import styles from "./reports.module.css";

export function SpeakingBenchmarkReports() {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<api.ReportFilters>({ verified_only: "true" });
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [summary, setSummary] = useState<api.ReportSummary | null>(null);
  const [rows, setRows] = useState<api.Comparison[]>([]);
  const [chartRows, setChartRows] = useState<api.Comparison[]>([]);
  const [outliers, setOutliers] = useState<api.Comparison[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([api.reportSummary(filters), api.reportSamples(filters, offset)]).then(([metrics, samples]) => {
      if (active) {
        setSummary(metrics);
        setRows(samples.items);
        setChartRows(samples.chart_points);
        setOutliers(samples.outliers ?? []);
        setTotal(samples.total);
        setError("");
      }
    }).catch(failure => {
      if (active) setError(failure instanceof Error ? failure.message : "REPORT_UNAVAILABLE");
    }).finally(() => {
      if (active) setBusy(false);
    });
    return () => { active = false; };
  }, [filters, offset]);

  function set(key: string, value: string) { setDraft(current => ({ ...current, [key]: value })); }
  const format = (value: number | null | undefined, percent = false) => value == null ? "—" : percent ? (value * 100).toFixed(1) + "%" : value.toFixed(2);

  return <>
    <PageHeading title={t("speakingReport.title")} description={t("speakingReport.description")} action={<Link className="btn btn-secondary" href="/admin/speaking-benchmark">{t("speakingReport.back")}</Link>} />
    <section className={lab.panel}><form onSubmit={e => { e.preventDefault(); setBusy(true); setOffset(0); setFilters({ ...draft }); }}>
      <div className={styles.filters}>
        <label className={lab.field}>{t("speakingReport.configuration")}<select className="select-field" value={draft.configuration ?? ""} onChange={e => set("configuration", e.target.value)}><option value="">{t("speakingEval.choose")}</option>{summary?.configurations.map(c => <option key={c} value={c}>{c.slice(0, 16)}</option>)}</select></label>
        <label className={lab.field}>{t("speakingReport.split")}<select className="select-field" value={draft.split ?? ""} onChange={e => set("split", e.target.value)}><option value="">{t("speakingReport.all")}</option><option>DEV</option><option>HOLDOUT</option></select></label>
        <label className={lab.field}>{t("speakingReport.status")}<select className="select-field" value={draft.status ?? ""} onChange={e => set("status", e.target.value)}><option value="">{t("speakingReport.all")}</option>{["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"].map(s => <option key={s}>{s}</option>)}</select></label>
        {([ ["model", "speakingReport.model"], ["rubric_version", "speakingReport.rubric"], ["prompt_version", "speakingReport.prompt"] ] as [string, TranslationKey][]).map(([key, label]) => <label className={lab.field} key={key}>{t(label)}<input className="field" value={draft[key] ?? ""} onChange={e => set(key, e.target.value)} /></label>)}
        {([ ["uploaded_from", "speakingReport.from"], ["uploaded_to", "speakingReport.to"] ] as [string, TranslationKey][]).map(([key, label]) => <label className={lab.field} key={key}>{t(label)}<input className="field" type="datetime-local" onChange={e => set(key, e.target.value ? new Date(e.target.value).toISOString() : "")} /></label>)}
      </div><label className={lab.check}><input type="checkbox" checked={draft.verified_only !== "false"} onChange={e => set("verified_only", String(e.target.checked))} />{t("speakingReport.verified")}</label><button className="btn btn-secondary" disabled={busy}>{t("speakingReport.apply")}</button>
    </form>{error && <p role="alert" className="notice notice-error">{error}</p>}{busy && <p role="status">{t("common.loading")}</p>}
    {summary && <>
      {summary.requires_configuration && <p className="notice" role="status">{t("speakingReport.chooseConfig")}</p>}{summary.leaking_speaker_count > 0 && <p className="notice">{t("speakingReport.leakage")} ({summary.leaking_speaker_count})</p>}
      <dl className={styles.counts}><div><dt>{t("speakingReport.uploaded")}</dt><dd>{summary.uploaded_samples}</dd></div><div><dt>{t("speakingReport.samples")}</dt><dd>{summary.eligible_samples}</dd></div><div><dt>{t("speakingReport.paired")} · Overall</dt><dd>{summary.criteria.overall?.count ?? 0}</dd></div><div><dt>{t("speakingReport.coverage")} · Overall</dt><dd>{format(summary.criteria.overall?.coverage_rate, true)}</dd></div></dl>
      <h2>{t("speakingReport.errors")}</h2><p className={lab.muted}>{t("speakingReport.insufficient")}</p>
      <div className={styles.tableWrap}><table className={lab.table}><thead><tr>{[t("speakingEval.criterion"), "n / eligible", "MAE", "RMSE", "Bias", "Exact", "±0.5", "±1.0", "Pearson", "Spearman", "QWK"].map(s => <th key={s}>{s}</th>)}</tr></thead><tbody>{criteria.map(key => { const m = summary.criteria[key]; return <tr key={key}><th scope="row">{key.toUpperCase()}</th><td>{m?.count ?? 0} / {m?.total_count ?? 0}</td><td>{format(m?.mae)}{m?.mae != null && <span className={styles.errorBar} style={{ width: (m.mae / 9 * 100) + "%" }} />}</td><td>{format(m?.rmse)}</td><td>{format(m?.signed_bias)}</td><td>{format(m?.exact_agreement, true)}</td><td>{format(m?.within_0_5, true)}</td><td>{format(m?.within_1_0, true)}</td><td title={m?.pearson_status}>{format(m?.pearson)}</td><td title={m?.spearman_status}>{format(m?.spearman)}</td><td title={m?.qwk_status}>{format(m?.quadratic_weighted_kappa)}</td></tr>; })}</tbody></table></div>
      <p className={lab.muted}>{t("speakingReport.chartLimit")}</p><ReportCharts rows={chartRows} />
      <details><summary>{t("speakingReport.splitCoverage")}</summary>{Object.entries(summary.split_metrics).map(([split, value]) => <p key={split}>{split} · {value.eligible_samples} · Overall {value.criteria?.overall?.count ?? 0}/{value.criteria?.overall?.total_count ?? 0} ({format(value.criteria?.overall?.coverage_rate, true)})</p>)}</details>
      {outliers.length > 0 && <details open><summary><strong>Global Outliers (Top {outliers.length} largest Overall differences across dataset)</strong></summary><div className={styles.tableWrap}><table className={lab.table}><thead><tr><th>{t("speakingLab.code")}</th><th>{t("speakingReport.status")}</th><th>{t("speakingEval.human")}</th><th>{t("speakingEval.ai")}</th><th>{t("speakingEval.difference")}</th></tr></thead><tbody>{outliers.map(r => <tr key={`outlier-${r.sample_id}`}><td><Link href={"/admin/speaking-benchmark/" + r.sample_id}>{r.code}</Link> · {r.split}<div className={lab.muted}>rev {r.review_revision ?? "—"} / label {r.label_revision}</div></td><td>{r.status}</td><td>{format(r.human.overall)}</td><td>{format(r.ai.overall)}</td><td>{format(r.differences.overall)}</td></tr>)}</tbody></table></div></details>}
      <h2>{t("speakingReport.rows")} ({total})</h2>{!rows.length && <p>{t("speakingReport.empty")}</p>}<div className={styles.tableWrap}><table className={lab.table}><thead><tr><th>{t("speakingLab.code")}</th><th>{t("speakingReport.status")}</th><th>{t("speakingEval.human")}</th><th>{t("speakingEval.ai")}</th><th>{t("speakingEval.difference")}</th></tr></thead><tbody>{rows.map(r => <tr key={r.sample_id}><td><Link href={"/admin/speaking-benchmark/" + r.sample_id}>{r.code}</Link> · {r.split}<div className={lab.muted}>rev {r.review_revision ?? "—"} / label {r.label_revision}</div></td><td>{r.status}</td><td>{format(r.human.overall)}</td><td>{format(r.ai.overall)}</td><td>{format(r.differences.overall)}</td></tr>)}</tbody></table></div>
      <div className={lab.actions}><button className="btn btn-secondary" disabled={busy || !offset} onClick={() => { setBusy(true); setOffset(Math.max(0, offset - 25)); }}>{t("speakingLab.previous")}</button><button className="btn btn-secondary" disabled={busy || offset + 25 >= total} onClick={() => { setBusy(true); setOffset(offset + 25); }}>{t("speakingLab.next")}</button>{!summary.requires_configuration && <><a className="btn btn-secondary" href={api.exportUrl(filters, "csv")}>{t("speakingReport.export")} CSV</a><a className="btn btn-secondary" href={api.exportUrl(filters, "json")}>{t("speakingReport.export")} JSON</a></>}</div>
    </>}
    </section>
  </>;
}
