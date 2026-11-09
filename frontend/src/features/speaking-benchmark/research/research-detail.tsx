"use client";

import Link from "next/link";
import { LabNavigation } from "../lab-navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-research";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { labError } from "../errors";
import { ExperimentControls } from "./experiment-controls";
import { ResearchResults } from "./research-results";
import { TranscriptComparison } from "./transcript-comparison";
import styles from "./research.module.css";

export function ResearchDetail({ experimentId, initialFilters = {} }: { experimentId: string; initialFilters?: Record<string, string> }) {
  const { t } = useTranslation(); const [experiment, setExperiment] = useState<api.ResearchExperiment | null>(null); const [report, setReport] = useState<api.ResearchReport | null>(null); const [error, setError] = useState(""); const [offset, setOffset] = useState(0); const [filters, setFilters] = useState<Record<string, string>>(initialFilters); const [draft, setDraft] = useState<Record<string, string>>(initialFilters);
  const loadVersion = useRef(0);
  const load = useCallback(async () => { const version = ++loadVersion.current; try { const [row, result] = await Promise.all([api.getExperiment(experimentId), api.experimentResults(experimentId, filters, offset)]); if (version !== loadVersion.current) return; setExperiment(row); setReport(result); setError(""); } catch (failure) { if (version === loadVersion.current) setError(labError(failure, t)); } }, [experimentId, filters, offset, t]);
  useEffect(() => { const tracker = loadVersion; void Promise.resolve().then(load); return () => { tracker.current++; }; }, [load]);
  useEffect(() => { if (!experiment || !["PENDING", "RUNNING"].includes(experiment.status)) return; const timer = window.setInterval(() => void load(), 4000); return () => window.clearInterval(timer); }, [experiment, load]);
  const changed = (row: api.ResearchExperiment) => { setExperiment(row); void load(); };
  function apply() { const active = Object.fromEntries(Object.entries(draft).filter(([, value]) => value !== "")); setFilters(active); setOffset(0); window.history.replaceState(null, "", `${window.location.pathname}?${new URLSearchParams(active)}`); }
  return <div className={styles.stack}><PageHeading eyebrow={t("speakingResearch.title")} title={experiment?.name ?? t("speakingResearch.experiments")} description={t("speakingResearch.description")} />
    <LabNavigation current="research" />
    {error && <p className="notice notice-error" role="alert">{error}<button className="btn btn-ghost" onClick={() => void load()}>{t("common.retry")}</button></p>}
    {!experiment ? <p role="status">{t("common.loading")}</p> : <>
      <ExperimentControls experiment={experiment} report={report} onChanged={changed} />
      <section className={styles.panel}><div className={styles.sectionHeading}><h2>{t("speakingResearch.filters")}</h2><span>{report?.reference_policy ?? "frozen"}</span></div><form className={styles.form} onSubmit={e => { e.preventDefault(); apply(); }}><div className={styles.filterGrid}>
        <label>{t("speakingLab.split")}<select className="field" value={draft.split ?? ""} onChange={e => setDraft(v => ({ ...v, split: e.target.value }))}><option value="">{t("speakingResearch.all")}</option><option>DEV</option><option>HOLDOUT</option></select></label>
        <label>Part<select className="field" value={draft.part ?? ""} onChange={e => setDraft(v => ({ ...v, part: e.target.value }))}><option value="">{t("speakingResearch.all")}</option>{[1, 2, 3].map(p => <option key={p}>{p}</option>)}</select></label>
        <label>{t("speakingResearch.provider")}<select className="field" value={draft.provider_key ?? ""} onChange={e => setDraft(v => ({ ...v, provider_key: e.target.value }))}><option value="">{t("speakingResearch.all")}</option>{experiment.configuration.variants.map(p => <option key={p.key}>{p.key}</option>)}</select></label><button className="btn btn-primary" type="submit">{t("speakingResearch.apply")}</button>
      </div><details><summary>{t("speakingResearch.advancedFilters")}</summary><div className={styles.grid}>{(["min_duration_ms", "max_duration_ms", "human_overall", "accent", "speaking_speed", "response_length"] as const).map(key => <label key={key}>{t(({ min_duration_ms: "speakingResearch.responseMinimum", max_duration_ms: "speakingResearch.responseMaximum", human_overall: "speakingResearch.humanBand", accent: "speakingResearch.accent", speaking_speed: "speakingResearch.speed", response_length: "speakingResearch.length" } as const)[key])}<input className="field" value={draft[key] ?? ""} onChange={e => setDraft(v => ({ ...v, [key]: e.target.value }))} /></label>)}</div>
      <label className={styles.check}><input type="checkbox" checked={draft.latest_references === "true"} onChange={e => setDraft(v => ({ ...v, latest_references: String(e.target.checked) }))} />{t("speakingResearch.latest")}</label></details></form>
      <div className={styles.filterFooter}><button className="btn btn-secondary" onClick={() => void load()}>{t("speakingResearch.refresh")}</button><div className={styles.actions}><span className={styles.caption}>{t("speakingResearch.export")}</span>{(["csv", "json"] as const).map(format => <a key={format} className="btn btn-secondary" aria-label={`${t("speakingResearch.export")} ${format.toUpperCase()}`} href={api.researchExportUrl(experimentId, format, filters)}>{format.toUpperCase()}</a>)}</div></div></section>
      {report && <><ResearchResults report={report} /><TranscriptComparison experiment={experiment} latest={filters.latest_references === "true"} /><section className={styles.panel}><h2>{t("speakingResearch.responses")} ({report.total})</h2><div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>{t("speakingLab.code")}</th><th>{t("speakingResearch.provider")}</th><th>Part</th><th>WER</th><th>{t("speakingResearch.status")}</th></tr></thead><tbody>{report.rows.map(row => <tr key={`${row.variant_id}:${row.segment_id}`}><td><Link href={`/admin/speaking-benchmark/${row.sample_id}`}>{row.code}</Link> · r{row.review_revision}</td><td>{row.provider}</td><td>{row.part}</td><td>{row.metrics.wer?.toFixed(3) ?? "—"}</td><td>{row.status}</td></tr>)}</tbody></table></div><div className={styles.actions}><button className="btn btn-secondary" disabled={!offset} onClick={() => setOffset(v => Math.max(0, v - 25))}>{t("speakingLab.previous")}</button><button className="btn btn-secondary" disabled={offset + 25 >= report.total} onClick={() => setOffset(v => v + 25)}>{t("speakingLab.next")}</button></div></section></>}
    </>}
  </div>;
}
