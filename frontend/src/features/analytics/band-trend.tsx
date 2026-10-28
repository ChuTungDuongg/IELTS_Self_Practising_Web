"use client";

import { useId, useMemo, useRef, useState } from "react";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import type { AnalyticsDashboard } from "@/lib/api/analytics";

const symbols = { READING: "●", LISTENING: "■", WRITING: "◆", SPEAKING: "+" } as const;
const skillOrder = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;
const colors = {
  READING: "var(--analytics-reading)", LISTENING: "var(--analytics-listening)",
  WRITING: "var(--analytics-writing)", SPEAKING: "var(--analytics-speaking)",
} as const;

export function BandTrend({ points }: { points: AnalyticsDashboard["trends"] }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const detailsId = useId();
  const tooltipId = useId();
  const hintId = useId();
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const pointControls = useRef<(HTMLButtonElement | null)[]>([]);
  const { dateFormatter, timestampFormatter } = useMemo(() => {
    const language = locale === "vi" ? "vi-VN" : "en-GB";
    return {
      dateFormatter: new Intl.DateTimeFormat(language, {
        timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "short", year: "numeric",
      }),
      timestampFormatter: new Intl.DateTimeFormat(language, {
        timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "short", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZoneName: "short",
      }),
    };
  }, [locale]);
  const { valid, series } = useMemo(() => {
    const valid = points
      .map((point, index) => ({ ...point, time: Date.parse(point.attempted_at), index, key: `${point.attempt_id}:${index}` }))
      .filter(point => skillOrder.includes(point.skill)
        && Number.isFinite(point.time)
        && typeof point.band_score === "number"
        && Number.isFinite(point.band_score)
        && point.band_score >= 0 && point.band_score <= 9)
      .sort((a, b) => a.time - b.time || a.index - b.index);
    const series = skillOrder.map(skill => ({ skill, observations: valid.filter(point => point.skill === skill) }))
      .filter(item => item.observations.length > 0);
    return { valid, series };
  }, [points]);
  const formattedPoints = useMemo(() => valid.map(point => ({ ...point, timestamp: timestampFormatter.format(point.time) })), [valid, timestampFormatter]);
  const first = valid[0]?.time ?? 0;
  const last = valid.at(-1)?.time ?? first;
  const x = (time: number) => first === last ? 360 : 44 + (time - first) / (last - first) * 632;
  const y = (band: number) => 18 + (9 - band) / 9 * 188;
  const date = (time: number) => dateFormatter.format(time);
  const ticks = date(first) === date(last) ? [first + (last - first) / 2] : [first, last];
  const selected = formattedPoints.find(point => point.key === (hovered ?? focused));
  const tabStop = valid.find(point => point.key === active)?.key ?? valid[0]?.key;

  return <>
    {series.length ? <ul className="trend-legend" aria-label={t("ui.skill")}>
      {series.map(({ skill }) => <li key={skill} data-skill={skill}><span className="trend-symbol" style={{ color: colors[skill] }} aria-hidden="true">{symbols[skill]}</span>{t(moduleTranslationKeys[skill])}</li>)}
    </ul> : null}
    <div className="trend-visual">
    <div className="trend-plot">
    <svg className="trend-chart" role="img" aria-label={t("analytics.trendLabel")} aria-describedby={hintId} aria-details={detailsId} viewBox="0 0 720 250">
      {[0, 3, 6, 9].map(tick => <g key={tick}>
        <line x1="44" x2="676" y1={y(tick)} y2={y(tick)} className="trend-grid" />
        <text x="24" y={y(tick) + 4} textAnchor="end">{tick}</text>
      </g>)}
      {series.map(({ skill, observations }) => observations.length > 1 ? <polyline key={skill} className="trend-series" data-skill={skill} points={observations.map(point => `${x(point.time)},${y(point.band_score)}`).join(" ")} fill="none" stroke={colors[skill]} strokeWidth="2" strokeLinejoin="round" vectorEffect="non-scaling-stroke" /> : null)}
      {formattedPoints.map(point => <g key={point.key} className="trend-mark" data-skill={point.skill} data-active={selected?.key === point.key || undefined} fill={colors[point.skill]}>
        <title>{t(moduleTranslationKeys[point.skill])} · {point.band_score.toFixed(1)} · {point.timestamp} · {point.test_title}</title>
        {point.skill === "READING" ? <circle cx={x(point.time)} cy={y(point.band_score)} r="4" />
          : point.skill === "LISTENING" ? <rect x={x(point.time) - 4} y={y(point.band_score) - 4} width="8" height="8" />
            : point.skill === "WRITING" ? <path d={`M${x(point.time)} ${y(point.band_score) - 5}l5 5-5 5-5-5Z`} />
              : <path d={`M${x(point.time) - 5} ${y(point.band_score)}h10m-5-5v10`} fill="none" stroke={colors[point.skill]} strokeWidth="2" />}
      </g>)}
      {valid.length ? ticks.map((time, index) => <text key={`${time}-${index}`} x={x(time)} y="235" textAnchor={ticks.length === 1 ? "middle" : index === 0 ? "start" : "end"}>{date(time)}</text>) : null}
    </svg>
    {formattedPoints.map((point, index) => <button key={point.key} ref={node => { pointControls.current[index] = node; }} type="button" className="trend-point" data-skill={point.skill} tabIndex={point.key === tabStop ? 0 : -1}
      style={{ left: `${x(point.time) / 720 * 100}%`, top: `${y(point.band_score) / 250 * 100}%` }}
      aria-label={`${t(moduleTranslationKeys[point.skill])} · ${point.band_score.toFixed(1)} · ${point.timestamp} · ${point.test_title}`}
      aria-describedby={selected?.key === point.key ? tooltipId : undefined}
      onMouseEnter={() => setHovered(point.key)} onMouseLeave={() => setHovered(null)}
      onFocus={() => { setFocused(point.key); setActive(point.key); }} onBlur={() => setFocused(null)}
      onClick={event => { event.currentTarget.focus(); setFocused(point.key); }}
      onKeyDown={event => {
        let next: number;
        switch (event.key) {
          case "ArrowLeft": next = Math.max(0, index - 1); break;
          case "ArrowRight": next = Math.min(valid.length - 1, index + 1); break;
          case "Home": next = 0; break;
          case "End": next = valid.length - 1; break;
          case "Escape": setHovered(null); setFocused(null); return;
          default: return;
        }
        event.preventDefault();
        setHovered(null);
        pointControls.current[next]?.focus();
      }}
    />)}
    </div>
    {selected ? <div className="trend-tooltip" id={tooltipId} role="tooltip" data-skill={selected.skill}>
      <strong>{t(moduleTranslationKeys[selected.skill])} · {selected.band_score.toFixed(1)}</strong>
      <time dateTime={selected.attempted_at}>{selected.timestamp}</time>
      <span>{selected.test_title}</span>
    </div> : null}
    </div>
    <p className="trend-hint" id={hintId}>{t("analytics.chartHint")}</p>
    <details className="trend-details" id={detailsId}>
      <summary>{t("ui.trendData")}</summary>
      <div className="data-table-scroll"><table>
        <caption className="sr-only">{t("analytics.trendLabel")}</caption>
        <thead><tr><th scope="col">{t("ui.attemptDate")}</th><th scope="col">{t("ui.skill")}</th><th scope="col">{t("ui.test")}</th><th scope="col" className="numeric-cell">{t("ui.band")}</th></tr></thead>
        <tbody>{formattedPoints.map(point => <tr key={point.key}>
          <td><time dateTime={point.attempted_at}>{point.timestamp}</time></td><td>{t(moduleTranslationKeys[point.skill])}</td><td>{point.test_title}</td><td className="numeric-cell">{point.band_score.toFixed(1)}</td>
        </tr>)}</tbody>
      </table></div>
    </details>
  </>;
}
