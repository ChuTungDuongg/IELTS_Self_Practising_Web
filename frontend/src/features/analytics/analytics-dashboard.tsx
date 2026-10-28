"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { AnalyticsIcon } from "@/components/ui/icons";
import { getAnalytics, type AnalyticsDashboard } from "@/lib/api/analytics";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import type { TranslationKey } from "@/lib/i18n/types";
import { analyticsPeriod, analyticsTimeZone, type AnalyticsRange } from "./analytics-scope";
import { AnalyticsCard, AnalyticsKpis, PracticeTimePanel, QuestionTypeAccuracy, RecentActivity, SkillIcon, SkillPerformance, WeakAreasPanel, skills } from "./analytics-panels";
import { AttemptComparisonPanel } from "./attempt-comparison";
import { BandTrend } from "./band-trend";
import "./analytics.css";

type Skill = typeof skills[number];
type Scope = { skill: Skill | "ALL"; range: AnalyticsRange };
const ranges: ReadonlyArray<{ value: AnalyticsRange; label: TranslationKey }> = [
  { value: "7", label: "analytics.last7" }, { value: "30", label: "analytics.last30" },
  { value: "90", label: "analytics.last90" }, { value: "ALL", label: "analytics.allHistory" },
];

export function AnalyticsDashboardView({ initial, asOf }: { initial: AnalyticsDashboard; asOf?: string }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  // Server and first client render share all-history scope. Freeze the server
  // calendar anchor so browser timezone cannot reinterpret the selected period.
  const [calendarAnchor] = useState(() => asOf ?? new Date().toISOString());
  const [data, setData] = useState(initial);
  const [scope, setScope] = useState<Scope>({ skill: "ALL", range: "ALL" });
  const [loading, setLoading] = useState(false);
  const [failedScope, setFailedScope] = useState<Scope | null>(null);
  const pending = useRef(false);

  async function changeScope(next: Scope) {
    if (pending.current) return;
    pending.current = true;
    setLoading(true);
    setFailedScope(null);
    try {
      const skill = next.skill === "ALL" ? undefined : next.skill;
      const result = next.range === "ALL" ? await getAnalytics(skill)
        : await getAnalytics(skill, undefined, analyticsPeriod(next.range, calendarAnchor));
      setData(result);
      setScope(next);
    } catch { setFailedScope(next); }
    finally { pending.current = false; setLoading(false); }
  }

  const period = analyticsPeriod(scope.range, calendarAnchor);
  const date = new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-GB", { timeZone: analyticsTimeZone, day: "2-digit", month: "2-digit", year: "numeric" });
  const periodLabel = period.start && period.end
    ? date.format(new Date(period.start)) + " – " + date.format(new Date(Date.parse(period.end) - 1)) : t("analytics.allHistory");

  return <div className="analytics-workspace" aria-busy={loading}>
    <PageHeading title={<span className="analytics-title"><span className="analytics-title-icon"><AnalyticsIcon /></span>{t("analytics.title")}</span>}
      description={t("analytics.subtitle")} action={<div className="analytics-date-controls">
        <div className="analytics-range" role="group" aria-label={t("analytics.dateFilter")}>
          {ranges.map(item => <button key={item.value} type="button" aria-pressed={scope.range === item.value} disabled={loading}
            onClick={() => void changeScope({ ...scope, range: item.value })}>{t(item.label)}</button>)}
        </div><span className="analytics-period-label">{periodLabel} · {t("analytics.calendarZone")}</span>
      </div>} />
    <div className="analytics-toolbar">
      <div className="analytics-skill-filter" role="group" aria-label={t("analytics.skillFilter")}>
        {(["ALL", ...skills] as const).map(skill => <button key={skill} type="button" disabled={loading}
          aria-pressed={scope.skill === skill} onClick={() => void changeScope({ ...scope, skill })}>
          {skill === "ALL" ? <AnalyticsIcon /> : <SkillIcon skill={skill} />}{skill === "ALL" ? t("analytics.all") : t(moduleTranslationKeys[skill])}
        </button>)}
      </div><span className="analytics-refresh-state" role="status">{loading ? t("ui.loading") : t("analytics.scopeSummary", { count: data.total_finalized_attempts })}</span>
    </div>
    {failedScope && <div className="notice notice-error" role="alert">{t("ui.filterFailed")} <button type="button" className="btn btn-ghost" disabled={loading} onClick={() => void changeScope(failedScope)}>{t("ui.retry")}</button></div>}
    <AnalyticsKpis data={data} />
    <div className="analytics-main-grid">
      <AnalyticsCard title="analytics.trend" description="analytics.trendDescription" icon={<AnalyticsIcon />} className="analytics-trend-panel">
        {data.trends.length ? <BandTrend key={scope.skill + ":" + scope.range} points={data.trends} /> : <div className="analytics-chart-empty">
          <div className="analytics-empty-grid" aria-hidden="true"><span>9</span><span>6</span><span>3</span><span>0</span></div>
          <div><p>{t("analytics.noBands")}</p><small>{t("analytics.emptyTrend")}</small><Link className="btn btn-secondary" href="/library">{t("analytics.startPracticing")}</Link></div>
        </div>}
      </AnalyticsCard><SkillPerformance bands={data.bands} />
    </div>
    <div className="analytics-secondary-grid"><QuestionTypeAccuracy items={data.question_types} skill={scope.skill} /><PracticeTimePanel data={data} /><RecentActivity attempts={data.attempts} /></div>
    <WeakAreasPanel items={data.weak_areas} />
    <AttemptComparisonPanel key={scope.skill + ":" + scope.range} attempts={data.attempts} disabled={loading} />
  </div>;
}
