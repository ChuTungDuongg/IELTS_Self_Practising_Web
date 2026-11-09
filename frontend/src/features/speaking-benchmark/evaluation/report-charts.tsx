"use client";

import { useId, useState } from "react";
import type { Comparison } from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./reports.module.css";
import { ReportTable } from "./report-tables";

type Chart = "distribution" | "scatter" | "signed";
const chartKinds: Chart[] = ["distribution", "scatter", "signed"];
const left = 44, right = 464, top = 24, bottom = 208;
function countScale(maximum: number) {
  const step = Math.max(1, Math.ceil(maximum / 3));
  const maximumTick = step * (Math.floor(maximum / step) + 1);
  return { maximum: maximumTick, ticks: Array.from({ length: maximumTick / step + 1 }, (_, index) => index * step) };
}

export function ReportCharts({ rows }: { rows: Comparison[] }) {
  const { t } = useTranslation();
  const id = useId();
  const [selected, setSelected] = useState<Chart>("distribution");
  const human = rows.filter(row => row.verified && row.human.overall != null);
  const paired = human.filter(row => row.ai.overall != null);
  const counts = Array.from({ length: 19 }, (_, index) => ({
    band: index / 2, human: human.filter(row => row.human.overall === index / 2).length,
    ai: paired.filter(row => row.ai.overall === index / 2).length,
  }));
  const errors = Array.from(new Set(paired.map(row => row.ai.overall! - row.human.overall!))).sort((a, b) => a - b).map(error => ({
    error, count: paired.filter(row => row.ai.overall! - row.human.overall! === error).length,
  }));
  const distributionScale = countScale(Math.max(0, ...counts.flatMap(count => [count.human, count.ai])));
  const errorScale = countScale(Math.max(0, ...errors.map(error => error.count)));
  const rawMin = Math.min(-1, ...errors.map(error => error.error));
  const rawMax = Math.max(1, ...errors.map(error => error.error));
  const errorStep = Math.max(0.5, Math.ceil((rawMax - rawMin) / 4 * 2) / 2);
  const errorMin = Math.floor(rawMin / errorStep) * errorStep;
  const errorMax = Math.ceil(rawMax / errorStep) * errorStep;
  const errorTicks = Array.from({ length: Math.floor((errorMax - errorMin) / errorStep) + 1 }, (_, index) => errorMin + index * errorStep);
  const errorX = (value: number) => left + 20 + (value - errorMin) / (errorMax - errorMin) * (right - left - 40);
  const bandX = (value: number) => left + 12 + value / 9 * (right - left - 24);
  const countY = (value: number, maximum: number) => bottom - value / maximum * (bottom - top);
  const canDraw = selected === "distribution" || paired.length > 0;
  if (!human.length) return <p className={styles.description}>{t("speakingReport.chartEmpty")}</p>;

  return <div className={styles.chartSection}>
    <fieldset className={styles.chartChoices}>
      <legend className="sr-only">{t("speakingReport.chartChoice")}</legend>
      {chartKinds.map(kind => <label key={kind} className={selected === kind ? styles.selectedChart : undefined}>
        <input type="radio" name={`${id}-chart`} value={kind} checked={selected === kind} onChange={() => setSelected(kind)} />{t(`speakingReport.${kind}`)}
      </label>)}
    </fieldset>
    <figure className={`${styles.chartFigure} ${!canDraw ? styles.noPlot : ""}`}>
      <figcaption className={styles.chartContext}>
        <h3>{t(`speakingReport.${selected}`)}</h3>
        <p id={`${id}-help`} className={styles.description}>{t(`speakingReport.${selected}Help`)}</p>
        <p className={styles.chartCount}>{t("speakingReport.chartCounts", { human: human.length, paired: paired.length })}</p>
        {selected === "distribution" && <div className={styles.legend}><span><i className={styles.humanSwatch} aria-hidden="true" />{t("speakingEval.human")}</span>{paired.length > 0 && <span><i className={styles.aiSwatch} aria-hidden="true" />{t("speakingEval.ai")}</span>}</div>}
        {paired.length > 0 && paired.length < 3 && <p className={styles.description}>{t("speakingReport.smallSample")}</p>}
      </figcaption>
      {canDraw ? <svg role="img" aria-label={t(`speakingReport.${selected}`)} aria-describedby={`${id}-help`} viewBox="0 0 480 250">
        {selected === "scatter" ? <>
          {[0, 3, 6, 9].map(value => <g key={value}>
            <line x1={left} y1={bottom - value / 9 * (bottom - top)} x2={right} y2={bottom - value / 9 * (bottom - top)} className={styles.axis} />
            <text x={left - 12} y={bottom - value / 9 * (bottom - top) + 4} textAnchor="end">{value}</text>
            <text x={left + value / 9 * (right - left)} y={bottom + 24} textAnchor="middle">{value}</text>
          </g>)}
          <line x1={left} y1={bottom} x2={right} y2={top} className={styles.reference} />
          {paired.map(row => <circle key={row.sample_id} cx={left + row.human.overall! / 9 * (right - left)} cy={bottom - row.ai.overall! / 9 * (bottom - top)} r="4" className={styles.ai}><title>{row.code}: {t("speakingEval.human")} {row.human.overall}; {t("speakingEval.ai")} {row.ai.overall}</title></circle>)}
        </> : <>
          {(selected === "distribution" ? distributionScale : errorScale).ticks.map(value => <g key={value}>
            <line x1={left} y1={countY(value, selected === "distribution" ? distributionScale.maximum : errorScale.maximum)} x2={right} y2={countY(value, selected === "distribution" ? distributionScale.maximum : errorScale.maximum)} className={styles.axis} />
            <text x={left - 12} y={countY(value, selected === "distribution" ? distributionScale.maximum : errorScale.maximum) + 4} textAnchor="end">{value}</text>
          </g>)}
          {selected === "distribution" ? <>
            {counts.map(count => <g key={count.band}>
              <rect x={bandX(count.band) - 8} y={countY(count.human, distributionScale.maximum)} width="7" height={bottom - countY(count.human, distributionScale.maximum)} className={styles.human} />
              <rect x={bandX(count.band) + 1} y={countY(count.ai, distributionScale.maximum)} width="7" height={bottom - countY(count.ai, distributionScale.maximum)} className={styles.ai} />
              <title>{count.band}: {t("speakingEval.human")} {count.human}; {t("speakingEval.ai")} {count.ai}</title>
            </g>)}
            {[0, 1.5, 3, 4.5, 6, 7.5, 9].map(value => <text key={value} x={bandX(value)} y={bottom + 24} textAnchor="middle">{value}</text>)}
          </> : <>
            <line x1={errorX(0)} y1={top} x2={errorX(0)} y2={bottom} className={styles.reference} />
            {errors.map(error => <rect key={error.error} x={errorX(error.error) - 10} y={countY(error.count, errorScale.maximum)} width="20" height={bottom - countY(error.count, errorScale.maximum)} className={styles.ai}><title>{error.error > 0 ? "+" : ""}{error.error}: {error.count}</title></rect>)}
            {errorTicks.map(value => <text key={value} x={errorX(value)} y={bottom + 24} textAnchor="middle">{value > 0 ? "+" : ""}{value}</text>)}
          </>}
        </>}
      </svg> : <p className={styles.description}>{t("speakingReport.noPairedChart")}</p>}
    </figure>
    {canDraw && <details className={styles.disclosure}>
      <summary>{t("speakingReport.chartData")}</summary>
      <ReportTable label={t(`speakingReport.${selected}`)}><table className={styles.table}>
        <caption className="sr-only">{t(`speakingReport.${selected}`)}</caption>
        <thead><tr>{(selected === "distribution" ? [t("speakingReport.band"), t("speakingEval.human"), t("speakingEval.ai")] : selected === "signed" ? [t("speakingReport.bias"), t("speakingReport.count")] : [t("speakingLab.code"), t("speakingEval.human"), t("speakingEval.ai")]).map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
        <tbody>{selected === "distribution" ? counts.map(count => <tr key={count.band}><th scope="row">{count.band}</th><td>{count.human}</td><td>{count.ai}</td></tr>) : selected === "signed" ? errors.map(error => <tr key={error.error}><th scope="row">{error.error > 0 ? "+" : ""}{error.error}</th><td>{error.count}</td></tr>) : paired.map(row => <tr key={row.sample_id}><th scope="row">{row.code}</th><td>{row.human.overall}</td><td>{row.ai.overall}</td></tr>)}</tbody>
      </table></ReportTable>
    </details>}
  </div>;
}
