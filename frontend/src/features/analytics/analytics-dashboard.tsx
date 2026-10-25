"use client";

import { useMemo, useState } from "react";
import { moduleTranslationKeys, questionTypeTranslationKeys } from "@/lib/i18n/translations";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { compareAttempts, getAnalytics, type AnalyticsDashboard, type AttemptComparison } from "@/lib/api/analytics";
import { formatDuration } from "@/features/exam/timer";
import type { TranslationKey } from "@/lib/i18n/types";
import { BandTrend } from "./band-trend";

type Filter = "ALL" | "READING" | "LISTENING" | "WRITING" | "SPEAKING";
const labels: Record<string, string> = { matching_headings: "Matching Headings", matching_information: "Matching Information", matching_features: "Matching Features", matching_sentence_endings: "Matching Sentence Endings", summary_completion_word_list: "Summary Completion — Word List", flow_chart_completion: "Flow-chart Completion", true_false_not_given: "True / False / Not Given", yes_no_not_given: "Yes / No / Not Given" };
const show = (value: number | null | undefined, digits = 1) => value === null || value === undefined ? "—" : value.toFixed(digits);
const writingMetricKeys: Readonly<Record<string, TranslationKey>> = {
  task1_overall: "analytics.task1Overall", task2_overall: "analytics.task2Overall",
  ta: "analytics.ta", cc: "analytics.cc", lr: "analytics.lr", gra: "analytics.gra",
};

export function AnalyticsDashboardView({ initial }: { initial: AnalyticsDashboard }) {
  const { t } = useTranslation();
  const [data, setData] = useState(initial); const [filter, setFilter] = useState<Filter>("ALL"); const [loading, setLoading] = useState(false);
  const [failedFilter, setFailedFilter] = useState<Filter | null>(null);
  const [comparing, setComparing] = useState(false);
  const [comparisonError, setComparisonError] = useState(false);
  const [left, setLeft] = useState(""); const [right, setRight] = useState(""); const [comparison, setComparison] = useState<AttemptComparison>();
  async function changeFilter(next: Filter) {
    if (loading) return;
    setLoading(true); setFailedFilter(null);
    try {
      setData(await getAnalytics(next === "ALL" ? undefined : next));
      setFilter(next);
    } catch { setFailedFilter(next); }
    finally { setLoading(false); }
  }
  async function compare() {
    if (!left || !right || left === right || comparing) return;
    setComparing(true); setComparisonError(false);
    try { setComparison(await compareAttempts(left, right)); }
    catch { setComparisonError(true); }
    finally { setComparing(false); }
  }
  const trends = useMemo(() => data.trends, [data.trends]);
  return <div className={loading ? "analytics-dashboard is-loading" : "analytics-dashboard"} aria-busy={loading}>
    <div className="analytics-filters" role="group" aria-label={t("analytics.skillFilter")}>{(["ALL", "READING", "LISTENING", "WRITING", "SPEAKING"] as Filter[]).map((item) => <button key={item} type="button" aria-pressed={filter === item} disabled={loading} className={filter === item ? "btn btn-primary" : "btn btn-secondary"} onClick={() => void changeFilter(item)}>{item === "ALL" ? t("analytics.all") : t(moduleTranslationKeys[item])}</button>)}</div>
    {failedFilter ? <div className="notice notice-error" role="alert">{t("ui.filterFailed")} <button type="button" className="btn btn-ghost" onClick={() => void changeFilter(failedFilter)}>{t("ui.retry")}</button></div> : null}
    <section className="analytics-summary"><Metric label={t("analytics.finalized")} value={String(data.total_finalized_attempts)} /><Metric label={t("analytics.practiceTime")} value={formatDuration(data.total_active_seconds)} /><Metric label={t("analytics.completedMocks")} value={String(data.completed_full_mocks)} /><Metric label={t("analytics.latestOverall")} value={show(data.latest_project_overall)} />{(["READING", "LISTENING", "WRITING", "SPEAKING"] as const).map((skill) => <Metric key={skill} label={t("analytics.skillBands", { skill: t(moduleTranslationKeys[skill]) })} value={`${show(data.bands[skill]?.latest)} / ${show(data.bands[skill]?.best)} / ${show(data.bands[skill]?.average, 2)}`} />)}</section>
    <section className="analytics-panel"><h2>{t("analytics.trend")}</h2>{trends.length ? <BandTrend points={trends} /> : <p className="analytics-empty">{t("analytics.noBands")}</p>}</section>
    <div className="analytics-two-column"><section className="analytics-panel"><h2>{t("analytics.typeAccuracy")}</h2>{data.question_types.length ? <ul className="analytics-list">{data.question_types.map((item) => <li key={item.question_type}><span>{questionTypeTranslationKeys[item.question_type] ? t(questionTypeTranslationKeys[item.question_type]) : labels[item.question_type] ?? item.question_type.replaceAll("_", " ")}</span><strong>{show(item.accuracy)}%</strong><small>{t("analytics.answers", { correct: item.correct, incorrect: item.incorrect, attempted: item.attempted })}</small></li>)}</ul> : <p className="analytics-empty">{t("analytics.noAnswers")}</p>}</section><section className="analytics-panel"><h2>{t("analytics.attention")}</h2>{data.weak_areas.length ? <ul className="analytics-list">{data.weak_areas.map((item) => <li key={item.question_type}><span>{questionTypeTranslationKeys[item.question_type] ? t(questionTypeTranslationKeys[item.question_type]) : labels[item.question_type] ?? item.question_type.replaceAll("_", " ")}</span><strong>{show(item.accuracy)}%</strong><small>{t("analytics.across", { count: item.attempted })}</small></li>)}</ul> : <p className="analytics-empty">{t("analytics.minimum")}</p>}</section></div>
    <section className="analytics-panel"><h2>{t("analytics.time")}</h2><p>{t("analytics.totalTime")} <strong>{formatDuration(data.total_active_seconds)}</strong> · {t("analytics.averageTime")} <strong>{data.average_attempt_seconds === null ? "—" : formatDuration(Math.round(data.average_attempt_seconds))}</strong></p>{data.content_timing.length ? <p>{t("analytics.timingSegments", { count: data.content_timing.length })}</p> : <p className="analytics-empty">{t("analytics.noTiming")}</p>}</section>
    <section className="analytics-panel"><h2>{t("analytics.compareTitle")}</h2><div className="analytics-compare-controls"><select aria-label={t("analytics.attemptA")} value={left} onChange={(event) => setLeft(event.target.value)}><option value="">{t("analytics.attemptA")}</option>{data.attempts.map((item) => <option key={item.attempt_id} value={item.attempt_id}>{item.label}</option>)}</select><select aria-label={t("analytics.attemptB")} value={right} onChange={(event) => setRight(event.target.value)}><option value="">{t("analytics.attemptB")}</option>{data.attempts.filter((item) => !left || item.skill === data.attempts.find((candidate) => candidate.attempt_id === left)?.skill).map((item) => <option key={item.attempt_id} value={item.attempt_id}>{item.label}</option>)}</select><button className="btn btn-primary" disabled={!left || !right || left === right || comparing} onClick={() => void compare()}>{comparing ? t("common.working") : t("analytics.compare")}</button></div>{comparisonError ? <p role="alert" className="notice notice-error">{t("ui.comparisonFailed")}</p> : null}{comparison ? <Comparison data={comparison} /> : null}</section>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>; }
function Comparison({ data }: { data: AttemptComparison }) { const { t } = useTranslation(); return <div className="comparison-grid">{([data.left, data.right] as const).map((side) => <article key={side.attempt_id}><h3>{side.test_title} · V{side.version_number}</h3><dl><div><dt>{t("analytics.band")}</dt><dd>{show(side.band_score)}</dd></div><div><dt>{t("analytics.raw")}</dt><dd>{side.raw_score === null || side.max_score === null ? "—" : `${side.raw_score} / ${side.max_score}`}</dd></div><div><dt>{t("analytics.active")}</dt><dd>{side.elapsed_seconds === null ? "—" : formatDuration(side.elapsed_seconds)}</dd></div><div><dt>{t("analytics.accuracy")}</dt><dd>{side.accuracy === null ? "—" : `${side.accuracy.toFixed(1)}%`}</dd></div>{side.writing ? Object.entries(side.writing).map(([key, value]) => <div key={key}><dt>{writingMetricKeys[key] ? t(writingMetricKeys[key]) : key.replaceAll("_", " ").toUpperCase()}</dt><dd>{show(value)}</dd></div>) : null}</dl></article>)}</div>; }
