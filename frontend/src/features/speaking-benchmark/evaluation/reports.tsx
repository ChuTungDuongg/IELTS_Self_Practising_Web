"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { LabNavigation } from "../lab-navigation";
import { ReportCharts } from "./report-charts";
import { CriterionMetrics, RecordingResults, SplitCoverage, reportNumber } from "./report-tables";
import styles from "./reports.module.css";

type ReportData = { summary: api.ReportSummary; samples: Awaited<ReturnType<typeof api.reportSamples>>; filters: api.ReportFilters };
const defaultFilters = () => ({ verified_only: "true" });
function localDateTime(value = "") {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export function SpeakingBenchmarkReports() {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<api.ReportFilters>(defaultFilters);
  const [filters, setFilters] = useState(draft);
  const [offset, setOffset] = useState(0);
  const [generation, setGeneration] = useState(0);
  const [data, setData] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([api.reportSummary(filters), api.reportSamples(filters, offset)]).then(([summary, samples]) => {
      if (active) { setData({ summary, samples, filters }); setError(""); }
    }).catch(failure => {
      if (active) setError(failure instanceof Error ? failure.message : "REPORT_UNAVAILABLE");
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [filters, offset, generation]);

  function set(key: string, value: string) { setDraft(current => ({ ...current, [key]: value })); }
  function apply(value: api.ReportFilters) { setBusy(true); setOffset(0); setFilters({ ...value }); }
  function changePage(value: number) {
    setBusy(true);
    setOffset(value);
    // A failed page keeps the previous result visible. Repeating that request
    // must still fetch, even when its offset is already held in state.
    setGeneration(current => current + 1);
  }
  const summary = data?.summary;
  const samples = data?.samples;
  const hasPairs = summary && Object.values(summary.criteria).some(metric => metric.count > 0);
  const hasMetricEvidence = summary && Object.values(summary.criteria).some(metric => metric.total_count > 0);

  return <div className={styles.reportPage}>
    <PageHeading title={t("speakingReport.title")} description={t("speakingReport.description")} />
    <LabNavigation current="evaluation" />
    <section className={styles.filterPanel} aria-label={t("speakingReport.apply")}>
      <form onSubmit={event => { event.preventDefault(); apply(draft); }}>
        <div className={styles.filters}>
          <label>{t("speakingReport.configuration")}<select className="select-field" value={draft.configuration ?? ""} onChange={event => set("configuration", event.target.value)}>
            <option value="">{t("speakingReport.chooseConfiguration")}</option>
            {summary?.configurations.map((configuration, index) => <option key={configuration} value={configuration} title={configuration}>{t("speakingReport.configurationOption", { number: index + 1, id: configuration.slice(0, 12) })}</option>)}
          </select></label>
          <label>{t("speakingReport.split")}<select className="select-field" value={draft.split ?? ""} onChange={event => set("split", event.target.value)}><option value="">{t("speakingReport.all")}</option><option>DEV</option><option>HOLDOUT</option></select></label>
          <label>{t("speakingReport.status")}<select className="select-field" value={draft.status ?? ""} onChange={event => set("status", event.target.value)}><option value="">{t("speakingReport.all")}</option>{(["COMPLETED", "PARTIAL", "FAILED", "CANCELLED"] as const).map(status => <option key={status} value={status}>{t(`speakingReport.status.${status}`)}</option>)}</select></label>
        </div>
        <details className={styles.filterDetails}><summary>{t("speakingReport.advancedFilters")}</summary>
          {(draft.configuration || summary?.configuration) && <p className={styles.description}>{t("speakingUx.fingerprint")}: <code>{draft.configuration || summary?.configuration}</code></p>}
          <div className={styles.filters}>
            {([ ["model", "model"], ["rubric_version", "rubric"], ["prompt_version", "prompt"] ] as const).map(([key, label]) => <label key={key}>{t(`speakingReport.${label}`)}<input className="field" value={draft[key] ?? ""} onChange={event => set(key, event.target.value)} /></label>)}
            {([ ["uploaded_from", "from"], ["uploaded_to", "to"] ] as const).map(([key, label]) => <label key={key}>{t(`speakingReport.${label}`)}<input className="field" type="datetime-local" value={localDateTime(draft[key])} onChange={event => set(key, event.target.value ? new Date(event.target.value).toISOString() : "")} /></label>)}
          </div>
        </details>
        <div className={styles.filterActions}>
          <label className={styles.check}><input type="checkbox" checked={draft.verified_only !== "false"} onChange={event => set("verified_only", String(event.target.checked))} />{t("speakingReport.verified")}</label>
          <div className={styles.actions}><button className="btn btn-primary" disabled={busy}>{t("speakingReport.apply")}</button><button className="btn btn-ghost" type="button" disabled={busy} onClick={() => { const value = defaultFilters(); setDraft(value); apply(value); }}>{t("speakingReport.clearFilters")}</button></div>
        </div>
      </form>
    </section>
    {busy && <p className={styles.description} role="status">{t(data ? "speakingReport.updating" : "common.loading")}</p>}
    {error && <div className="notice notice-error"><p role="alert">{t("speakingReport.loadFailed")}</p>{data && <p>{t("speakingReport.keptResults")}</p>}<button className="btn btn-secondary" disabled={busy} onClick={() => { setBusy(true); setGeneration(value => value + 1); }}>{t("common.retry")}</button><details><summary>{t("speakingReport.diagnostics")}</summary><code>{error}</code></details></div>}
    {summary && samples && <div className={styles.reportBody} aria-busy={busy}>
      <section className={styles.section}>
        <h2>{t("speakingReport.overview")}</h2>
        <dl className={styles.counts}>{([
          ["uploaded", summary.uploaded_samples], ["samples", summary.eligible_samples],
          ["paired", summary.criteria.overall?.count ?? 0], ["coverage", reportNumber(summary.criteria.overall?.coverage_rate, true)],
        ] as const).map(([label, value]) => <div key={label}><dt>{t(`speakingReport.${label}`)}</dt><dd className={value === "—" ? styles.unavailable : undefined}>{value}</dd></div>)}</dl>
        {summary.requires_configuration ? <p className="notice" role="status">{t("speakingReport.chooseConfig")}</p> : hasPairs && <p className={styles.description}>{t("speakingReport.pairedSummary", { count: summary.criteria.overall?.count ?? 0 })}</p>}
        {summary.leaking_speaker_count > 0 && <p className="notice">{t("speakingReport.leakage")} ({summary.leaking_speaker_count})</p>}
      </section>
      {!summary.requires_configuration && <>
        <section className={styles.section}>
          {hasMetricEvidence ? <><h2>{t("speakingReport.errors")}</h2>{!hasPairs && <p className={styles.description}>{t("speakingReport.emptyHelp")}</p>}<CriterionMetrics summary={summary} /></> : <div className={styles.empty}>
            <h2>{t("speakingReport.emptyTitle")}</h2><p>{t("speakingReport.emptyHelp")}</p>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark">{t("speakingReport.openRecordings")}</Link>
          </div>}
        </section>
        {(hasPairs || samples.chart_points.length > 0) && <section className={styles.section}>
          <h2>{t("speakingReport.chartsTitle")}</h2>
          <ReportCharts rows={samples.chart_points} />
          <p className={styles.description}>{t("speakingReport.chartSource", { count: samples.chart_points.length })}{samples.chart_sampled && <> {t("speakingReport.chartSampled", { limit: samples.chart_limit })}</>}</p>
        </section>}
        {(samples.outliers?.length ?? 0) > 0 && <details className={styles.disclosure}>
          <summary>{t("speakingReport.outliers")} ({samples.outliers!.length})</summary><p className={styles.description}>{t("speakingReport.outliersHelp")}</p>
          <RecordingResults rows={samples.outliers!} caption={t("speakingReport.outliers")} />
        </details>}
        {samples.items.length > 0 && <section className={styles.section}>
          <h2>{t("speakingReport.rows")} <span className={styles.total}>({samples.total})</span></h2>
          <RecordingResults rows={samples.items} caption={t("speakingReport.rows")} />
        </section>}
        {!samples.items.length && hasPairs && <p className={styles.description}>{t("speakingReport.empty")}</p>}
        {Object.values(summary.split_metrics).some(value => value.eligible_samples > 0 || value.displayed_samples > 0) && <SplitCoverage summary={summary} />}
        <footer className={styles.footer}>
          {samples.total > 0 && <div><p className={styles.description}>{t("speakingReport.pagination", { from: samples.offset + 1, to: Math.min(samples.offset + samples.items.length, samples.total), total: samples.total })}</p><div className={styles.actions}>
            <button className="btn btn-secondary" disabled={busy || !samples.offset} onClick={() => changePage(Math.max(0, samples.offset - 25))}>{t("speakingLab.previous")}</button>
            <button className="btn btn-secondary" disabled={busy || samples.offset + 25 >= samples.total} onClick={() => changePage(samples.offset + 25)}>{t("speakingLab.next")}</button>
          </div></div>}
          {!busy && <div className={styles.actions}>
            <a className="btn btn-ghost" href={api.exportUrl(data!.filters, "csv")}>{t("speakingReport.export")} CSV</a>
            <a className="btn btn-ghost" href={api.exportUrl(data!.filters, "json")}>{t("speakingReport.export")} JSON</a>
          </div>}
        </footer>
      </>}
    </div>}
  </div>;
}
