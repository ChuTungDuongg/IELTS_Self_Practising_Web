"use client";

import { useRef, useState } from "react";
import { TransferIcon } from "@/components/ui/icons";
import { formatDuration } from "@/features/exam/timer";
import { compareAttempts, type AnalyticsDashboard, type AttemptComparison } from "@/lib/api/analytics";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import type { TranslationKey } from "@/lib/i18n/types";
import { AnalyticsCard, showBand } from "./analytics-panels";
import { analyticsTimeZone } from "./analytics-scope";

const writingMetricKeys: Readonly<Record<string, TranslationKey>> = {
  task1_overall: "analytics.task1Overall", task2_overall: "analytics.task2Overall",
  ta: "analytics.ta", cc: "analytics.cc", lr: "analytics.lr", gra: "analytics.gra",
};

export function AttemptComparisonPanel({ attempts, disabled }: { attempts: AnalyticsDashboard["attempts"]; disabled: boolean }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [comparison, setComparison] = useState<AttemptComparison>();
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState(false);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const leftSkill = attempts.find(item => item.attempt_id === left)?.skill;
  const date = new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-GB", { timeZone: analyticsTimeZone, dateStyle: "short", timeStyle: "short" });
  const optionLabel = (item: AnalyticsDashboard["attempts"][number]) => item.test_title
    ? `${item.test_title} · ${t(moduleTranslationKeys[item.skill])} · ${date.format(new Date(item.finished_at))}` : item.label;

  function select(side: "left" | "right", id: string) {
    generation.current++;
    setComparison(undefined);
    setError(false);
    if (side === "left") { setLeft(id); setRight(""); }
    else setRight(id);
  }
  async function compare() {
    if (!left || !right || left === right || inFlight.current || disabled) return;
    const current = ++generation.current;
    inFlight.current = true;
    setComparing(true);
    setError(false);
    try {
      const result = await compareAttempts(left, right);
      if (current === generation.current) setComparison(result);
    } catch { if (current === generation.current) setError(true); }
    finally { inFlight.current = false; setComparing(false); }
  }

  return <AnalyticsCard title="analytics.compareTitle" description="analytics.comparisonDescription" icon={<TransferIcon />}>
    <div className="analytics-comparison-controls">
      <label><span>{t("analytics.attemptA")}</span><select aria-label={t("analytics.attemptA")} value={left} disabled={disabled || comparing} onChange={event => select("left", event.target.value)}>
        <option value="">{t("analytics.attemptA")}</option>{attempts.map(item => <option key={item.attempt_id} value={item.attempt_id}>{optionLabel(item)}</option>)}
      </select></label>
      <label><span>{t("analytics.attemptB")}</span><select aria-label={t("analytics.attemptB")} value={right} disabled={disabled || comparing} onChange={event => select("right", event.target.value)}>
        <option value="">{t("analytics.attemptB")}</option>{attempts.filter(item => !leftSkill || item.skill === leftSkill).map(item => <option key={item.attempt_id} value={item.attempt_id} disabled={item.attempt_id === left}>{optionLabel(item)}</option>)}
      </select></label>
      <button type="button" className="btn btn-primary" disabled={disabled || !left || !right || left === right || comparing} onClick={() => void compare()}>{comparing ? t("common.working") : t("analytics.compare")}</button>
    </div>
    {!attempts.length && <p className="analytics-empty-message">{t("analytics.noComparison")}</p>}
    {error && <p role="alert" className="notice notice-error">{t("ui.comparisonFailed")}</p>}
    {comparison && <div className="analytics-comparison-grid">{[comparison.left, comparison.right].map(side => <article key={side.attempt_id}>
      <span className="analytics-comparison-skill">{t(moduleTranslationKeys[side.skill])}</span><h3>{side.test_title}</h3>
      <dl><div><dt>{t("analytics.band")}</dt><dd>{showBand(side.band_score)}</dd></div>
        <div><dt>{t("analytics.raw")}</dt><dd>{side.raw_score == null || side.max_score == null ? "—" : `${side.raw_score} / ${side.max_score}`}</dd></div>
        <div><dt>{t("analytics.active")}</dt><dd>{side.elapsed_seconds == null ? "—" : formatDuration(side.elapsed_seconds)}</dd></div>
        <div><dt>{t("analytics.accuracy")}</dt><dd>{side.accuracy == null ? "—" : `${side.accuracy.toFixed(1)}%`}</dd></div>
        {side.writing && Object.entries(side.writing).map(([key, value]) => <div key={key}><dt>{writingMetricKeys[key] ? t(writingMetricKeys[key]) : key.replaceAll("_", " ").toUpperCase()}</dt><dd>{showBand(value)}</dd></div>)}
      </dl>
    </article>)}</div>}
  </AnalyticsCard>;
}
