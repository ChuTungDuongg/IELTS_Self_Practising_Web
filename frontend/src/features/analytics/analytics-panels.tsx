"use client";

import { useId, useMemo, type ReactNode } from "react";
import Link from "next/link";
import { AlertIcon, AnalyticsIcon, ArrowIcon, BuilderIcon, HeadphonesIcon, HistoryIcon, ReadingIcon } from "@/components/ui/icons";
import { formatDuration } from "@/features/exam/timer";
import type { AnalyticsDashboard } from "@/lib/api/analytics";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys, questionTypeTranslationKeys } from "@/lib/i18n/translations";
import type { TranslationKey } from "@/lib/i18n/types";
import { analyticsTimeZone } from "./analytics-scope";

export const skills = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;
type Skill = typeof skills[number];
type Accuracy = AnalyticsDashboard["question_types"][number];
export const showBand = (value: number | null | undefined, digits = 1) => value == null ? "—" : value.toFixed(digits);

export function SkillIcon({ skill }: { skill: Skill }) {
  if (skill === "READING") return <ReadingIcon />;
  if (skill === "LISTENING") return <HeadphonesIcon />;
  if (skill === "WRITING") return <BuilderIcon />;
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M6 11v1a6 6 0 0 0 12 0v-1M12 18v3M9 21h6" /></svg>;
}

function ClockIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>;
}
function TrophyIcon() {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3h8v8a4 4 0 0 1-8 0ZM8 5H4v3a4 4 0 0 0 4 4M16 5h4v3a4 4 0 0 1-4 4M12 15v5M8 21h8" /></svg>;
}

export function AnalyticsCard({ title, description, icon, action, children, className = "" }: {
  title: TranslationKey; description?: TranslationKey; icon?: ReactNode; action?: ReactNode; children: ReactNode; className?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  return <section className={`analytics-card ${className}`} aria-labelledby={id}>
    <header className="analytics-card-heading"><div><h2 id={id}>{icon}{t(title)}</h2>{description && <p>{t(description)}</p>}</div>{action}</header>{children}
  </section>;
}

export function AnalyticsKpis({ data }: { data: AnalyticsDashboard }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const number = new Intl.NumberFormat(locale);
  const mock = data.latest_full_mock?.overall_band;
  const overall = mock ?? data.latest_project_overall;
  const metrics = [
    { label: "analytics.finalized", value: number.format(data.total_finalized_attempts), icon: <BuilderIcon />, note: "analytics.finalizedNote" },
    { label: "analytics.practiceTime", value: formatDuration(data.total_active_seconds), icon: <ClockIcon />, note: "analytics.activeTimeNote" },
    { label: "analytics.completedMocks", value: number.format(data.completed_full_mocks), icon: <TrophyIcon />, note: "analytics.mockScope" },
    { label: "analytics.latestOverall", value: showBand(overall), icon: <AnalyticsIcon />, note: mock != null ? "analytics.mockOverallNote" : "analytics.practiceOverallNote" },
  ] as const;
  return <div className="analytics-kpi-grid">{metrics.map(metric => <article className="analytics-kpi" key={metric.label}>
    <div className="analytics-kpi-icon">{metric.icon}</div><div><span>{t(metric.label)}</span><strong>{metric.value}</strong><small>{t(metric.note)}</small></div>
  </article>)}</div>;
}

export function SkillPerformance({ bands }: { bands: AnalyticsDashboard["bands"] }) {
  const { t } = useTranslation();
  return <AnalyticsCard title="analytics.skillPerformance" description="analytics.allSkillsInPeriod" icon={<AnalyticsIcon />}>
    <ul className="analytics-skill-bands">{skills.map(skill => {
      const band = bands[skill];
      return <li key={skill} data-skill={skill}>
        <div className="analytics-skill-label"><span className="analytics-skill-icon"><SkillIcon skill={skill} /></span><span>{t(moduleTranslationKeys[skill])}</span><strong>{showBand(band?.average, 2)}</strong></div>
        {band?.average != null ? <div className="analytics-bar" role="progressbar" aria-label={t(moduleTranslationKeys[skill])} aria-valuemin={0} aria-valuemax={9} aria-valuenow={band.average}><span style={{ width: `${Math.min(100, Math.max(0, band.average / 9 * 100))}%` }} /></div> : <span className="analytics-band-unavailable">{t("analytics.notGraded")}</span>}
      </li>;
    })}</ul>
    <details className="analytics-disclosure"><summary>{t("analytics.bandBreakdown")}</summary><dl className="analytics-band-breakdown">{skills.map(skill => <div key={skill}><dt>{t(moduleTranslationKeys[skill])}</dt><dd>{showBand(bands[skill]?.latest)} / {showBand(bands[skill]?.best)} / {showBand(bands[skill]?.average, 2)}</dd></div>)}</dl></details>
  </AnalyticsCard>;
}

function AccuracyRows({ items, attention = false }: { items: Accuracy[]; attention?: boolean }) {
  const { t } = useTranslation();
  return <ul className={`analytics-accuracy-list ${attention ? "analytics-attention-list" : ""}`}>{items.map(item => <li key={item.question_type}>
    <div><span>{questionTypeTranslationKeys[item.question_type] ? t(questionTypeTranslationKeys[item.question_type]) : item.question_type.replaceAll("_", " ")}</span><strong>{item.accuracy == null ? "—" : `${item.accuracy.toFixed(1)}%`}</strong></div>
    {item.accuracy != null && <div className="analytics-bar" aria-hidden="true"><span style={{ width: `${Math.min(100, Math.max(0, item.accuracy))}%` }} /></div>}
    <small>{t("analytics.answers", { correct: item.correct, incorrect: item.incorrect, attempted: item.attempted })}</small>
  </li>)}</ul>;
}

export function QuestionTypeAccuracy({ items, skill }: { items: Accuracy[]; skill: Skill | "ALL" }) {
  const { t } = useTranslation();
  return <AnalyticsCard title="analytics.typeAccuracy" description="analytics.accuracyDescription" icon={<AnalyticsIcon />}>
    {items.length ? <><AccuracyRows items={items.slice(0, 5)} />{items.length > 5 && <details className="analytics-disclosure"><summary>{t("analytics.moreTypes", { count: items.length - 5 })}</summary><AccuracyRows items={items.slice(5)} /></details>}</>
      : <p className="analytics-empty-message">{t(skill === "WRITING" || skill === "SPEAKING" ? "analytics.accuracyNotApplicable" : "analytics.noAnswers")}</p>}
  </AnalyticsCard>;
}

export function PracticeTimePanel({ data }: { data: AnalyticsDashboard }) {
  const { t } = useTranslation();
  return <AnalyticsCard title="analytics.time" description="analytics.timingDescription" icon={<ClockIcon />}>
    <div className="analytics-average-time"><span>{t("analytics.recordedAverage")}</span><strong>{data.average_attempt_seconds == null ? "—" : formatDuration(Math.round(data.average_attempt_seconds))}</strong></div>
    <p className="analytics-time-note">{t("analytics.activeTimeNote")}</p>
    <div className="analytics-timing-note">{data.content_timing.length ? <><strong>{t("analytics.timingSegments", { count: data.content_timing.length })}</strong><p>{t("analytics.navigationTimingNote")}</p></> : <p>{t("analytics.noTiming")}</p>}</div>
  </AnalyticsCard>;
}

export function RecentActivity({ attempts }: { attempts: AnalyticsDashboard["attempts"] }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const recent = useMemo(() => [...attempts].sort((a, b) => Date.parse(b.finished_at) - Date.parse(a.finished_at) || a.attempt_id.localeCompare(b.attempt_id)).slice(0, 5), [attempts]);
  const date = new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-GB", { timeZone: analyticsTimeZone, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  return <AnalyticsCard title="analytics.recentActivity" description="analytics.recentDescription" icon={<HistoryIcon />} action={<Link className="analytics-text-link" href="/history">{t("analytics.viewAll")}<ArrowIcon /></Link>}>
    {recent.length ? <ul className="analytics-activity-list">{recent.map(item => <li key={item.attempt_id} data-skill={item.skill}>
      <Link href={`/review/${encodeURIComponent(item.attempt_id)}`}>
        <span className="analytics-skill-icon"><SkillIcon skill={item.skill} /></span>
        <span className="analytics-activity-detail"><strong>{item.test_title ?? item.label}</strong><small>{t(moduleTranslationKeys[item.skill])} · <time dateTime={item.finished_at}>{date.format(new Date(item.finished_at))}</time></small></span>
        <span className="analytics-activity-score">{item.band_score == null ? t("analytics.notGraded") : showBand(item.band_score)}</span>
      </Link>
    </li>)}</ul> : <p className="analytics-empty-message">{t("analytics.noActivity")}</p>}
  </AnalyticsCard>;
}

export function WeakAreasPanel({ items }: { items: Accuracy[] }) {
  const { t } = useTranslation();
  const eligible = items.filter(item => item.attempted >= 5 && item.accuracy != null);
  return <AnalyticsCard title="analytics.attention" description="analytics.attentionDescription" icon={<AlertIcon />} className="analytics-attention-panel">
    {eligible.length ? <><AccuracyRows items={eligible.slice(0, 3)} attention />{eligible.length > 3 && <details className="analytics-disclosure"><summary>{t("analytics.moreTypes", { count: eligible.length - 3 })}</summary><AccuracyRows items={eligible.slice(3)} attention /></details>}</>
      : <p className="analytics-empty-message">{t("analytics.minimum")}</p>}
  </AnalyticsCard>;
}
