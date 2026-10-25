"use client";

import { useId } from "react";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import type { AnalyticsDashboard } from "@/lib/api/analytics";

const symbols = { READING: "●", LISTENING: "■", WRITING: "◆", SPEAKING: "+" } as const;

export function BandTrend({ points }: { points: AnalyticsDashboard["trends"] }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const detailsId = useId();
  const formatter = new Intl.DateTimeFormat(locale === "vi" ? "vi-VN" : "en-GB", {
    timeZone: "Asia/Ho_Chi_Minh", day: "2-digit", month: "short", year: "numeric",
  });
  const dated = points.map(point => ({ ...point, time: Date.parse(point.attempted_at) }));
  const valid = dated.filter(point => Number.isFinite(point.time)).sort((a, b) => a.time - b.time);
  const first = valid[0]?.time ?? 0;
  const last = valid.at(-1)?.time ?? first;
  const skills = [...new Set(valid.map(point => point.skill))];
  const x = (time: number) => first === last ? 360 : 44 + (time - first) / (last - first) * 632;
  const y = (band: number) => 18 + (9 - band) / 9 * 188;
  const date = (time: number) => Number.isFinite(time) ? formatter.format(time) : "—";
  const ticks = first === last ? [first] : [first, last];

  return <>
    {skills.length > 1 ? <ul className="trend-legend" aria-label={t("ui.skill")}>
      {skills.map(skill => <li key={skill}><span aria-hidden="true">{symbols[skill]}</span>{t(moduleTranslationKeys[skill])}</li>)}
    </ul> : null}
    <svg className="trend-chart" role="img" aria-label={t("analytics.trendLabel")} aria-describedby={detailsId} viewBox="0 0 720 250">
      {[0, 3, 6, 9].map(tick => <g key={tick}>
        <line x1="44" x2="676" y1={y(tick)} y2={y(tick)} className="trend-grid" />
        <text x="24" y={y(tick) + 4} textAnchor="end">{tick}</text>
      </g>)}
      {skills.length === 1 && valid.length > 1 ? <polyline points={valid.map(point => `${x(point.time)},${y(point.band_score)}`).join(" ")} fill="none" stroke="var(--accent)" strokeWidth="2" /> : null}
      {valid.map(point => <g key={point.attempt_id} fill="var(--accent)">
        <title>{t(moduleTranslationKeys[point.skill])} · {point.band_score.toFixed(1)} · {date(point.time)} · {point.test_title}</title>
        {point.skill === "READING" ? <circle cx={x(point.time)} cy={y(point.band_score)} r="4" />
          : point.skill === "LISTENING" ? <rect x={x(point.time) - 4} y={y(point.band_score) - 4} width="8" height="8" />
            : point.skill === "WRITING" ? <path d={`M${x(point.time)} ${y(point.band_score) - 5}l5 5-5 5-5-5Z`} />
              : <path d={`M${x(point.time) - 5} ${y(point.band_score)}h10m-5-5v10`} fill="none" stroke="var(--accent)" strokeWidth="2" />}
      </g>)}
      {valid.length ? ticks.map((time, index) => <text key={`${time}-${index}`} x={x(time)} y="235" textAnchor={ticks.length === 1 ? "middle" : index === 0 ? "start" : "end"}>{date(time)}</text>) : null}
    </svg>
    <details className="trend-details" id={detailsId}>
      <summary>{t("ui.trendData")}</summary>
      <div className="data-table-scroll"><table>
        <caption className="sr-only">{t("analytics.trendLabel")}</caption>
        <thead><tr><th scope="col">{t("ui.attemptDate")}</th><th scope="col">{t("ui.skill")}</th><th scope="col">{t("ui.test")}</th><th scope="col" className="numeric-cell">{t("ui.band")}</th></tr></thead>
        <tbody>{dated.map(point => <tr key={point.attempt_id}>
          <td><time dateTime={point.attempted_at}>{date(point.time)}</time></td><td>{t(moduleTranslationKeys[point.skill])}</td><td>{point.test_title}</td><td className="numeric-cell">{point.band_score.toFixed(1)}</td>
        </tr>)}</tbody>
      </table></div>
    </details>
  </>;
}
