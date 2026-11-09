"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { Comparison, ReportSummary } from "@/lib/api/speaking-benchmark-grading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationFunction } from "@/lib/i18n/types";
import styles from "./reports.module.css";

const criteria = ["overall", "fc", "lr", "gra", "pr"] as const;
export const reportNumber = (value: number | null | undefined, percent = false) => value == null ? "—" : percent ? `${(value * 100).toFixed(1)}%` : value.toFixed(2);
export const signedNumber = (value: number | null | undefined) => value == null ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
const criterionName = (key: typeof criteria[number], t: TranslationFunction) => t(key === "overall" ? "speakingReport.overall" : `speakingReviewer.${key}`);
const statusName = (status: string, t: TranslationFunction) => {
  if (status === "COMPLETED" || status === "PARTIAL" || status === "FAILED" || status === "CANCELLED" || status === "NO_RUN") return t(`speakingReport.status.${status}`);
  return status;
};

export function ReportTable({ label, children }: { label: string; children: ReactNode }) {
  const { t } = useTranslation();
  return <div><p className={styles.scrollHint}>{t("speakingReport.scrollTable")}</p><div className={styles.tableWrap} role="region" aria-label={label} tabIndex={0}>{children}</div></div>;
}

export function CriterionMetrics({ summary }: { summary: ReportSummary }) {
  const { t } = useTranslation();
  return <>
    <ReportTable label={t("speakingReport.errors")}><table className={styles.table}>
      <caption className="sr-only">{t("speakingReport.errors")}</caption>
      <thead><tr><th scope="col">{t("speakingEval.criterion")}</th><th scope="col">{t("speakingReport.pairs")}</th><th scope="col">{t("speakingReport.meanGap")}</th><th scope="col">{t("speakingReport.bias")}</th><th scope="col">{t("speakingReport.withinHalf")}</th></tr></thead>
      <tbody>{criteria.map(key => {
        const metric = summary.criteria[key];
        return <tr key={key}><th scope="row">{criterionName(key, t)}</th><td>{metric?.count ?? 0} / {metric?.total_count ?? 0}</td><td>{reportNumber(metric?.mae)}</td><td>{signedNumber(metric?.signed_bias)}</td><td>{reportNumber(metric?.within_0_5, true)}</td></tr>;
      })}</tbody>
    </table></ReportTable>
    <p className={styles.description}>{t("speakingReport.metricHelp")}</p>
    <details className={styles.disclosure}>
      <summary>{t("speakingReport.advancedStats")}</summary>
      <p className={styles.description}>{t("speakingReport.insufficient")}</p>
      <ReportTable label={t("speakingReport.advancedStats")}><table className={`${styles.table} ${styles.advancedTable}`}>
        <caption className="sr-only">{t("speakingReport.advancedStats")}</caption>
        <thead><tr><th scope="col">{t("speakingEval.criterion")}</th>{(["rmse", "exact", "withinOne", "pearson", "spearman", "kappa"] as const).map(key => <th key={key} scope="col">{t(`speakingReport.${key}`)}</th>)}</tr></thead>
        <tbody>{criteria.map(key => {
          const metric = summary.criteria[key];
          return <tr key={key}><th scope="row">{criterionName(key, t)}</th><td>{reportNumber(metric?.rmse)}</td><td>{reportNumber(metric?.exact_agreement, true)}</td><td>{reportNumber(metric?.within_1_0, true)}</td><td title={metric?.pearson_status}>{reportNumber(metric?.pearson)}</td><td title={metric?.spearman_status}>{reportNumber(metric?.spearman)}</td><td title={metric?.qwk_status}>{reportNumber(metric?.quadratic_weighted_kappa)}</td></tr>;
        })}</tbody>
      </table></ReportTable>
    </details>
  </>;
}

export function RecordingResults({ rows, caption }: { rows: Comparison[]; caption: string }) {
  const { t } = useTranslation();
  return <ReportTable label={caption}><table className={styles.table}>
    <caption className="sr-only">{caption}</caption>
    <thead><tr><th scope="col">{t("speakingLab.code")}</th><th scope="col">{t("speakingReport.status")}</th><th scope="col">{t("speakingEval.human")}</th><th scope="col">{t("speakingEval.ai")}</th><th scope="col">{t("speakingReport.bias")}</th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.sample_id}>
      <th scope="row"><Link href={`/admin/speaking-benchmark/${row.sample_id}`}>{row.code}</Link><span className={styles.rowMeta}>{row.split} · {t("speakingReport.versions", { review: row.review_revision ?? "—", label: row.label_revision ?? "—" })}</span></th>
      <td className={styles.statusCell}>{statusName(row.status, t)}</td><td>{reportNumber(row.human.overall)}</td><td>{reportNumber(row.ai.overall)}</td><td>{signedNumber(row.differences.overall)}</td>
    </tr>)}</tbody>
  </table></ReportTable>;
}

export function SplitCoverage({ summary }: { summary: ReportSummary }) {
  const { t } = useTranslation();
  return <details className={styles.disclosure}>
    <summary>{t("speakingReport.splitCoverage")}</summary>
    {!Object.keys(summary.split_metrics).length ? <p className={styles.description}>{t("speakingReport.noCoverage")}</p> : <ReportTable label={t("speakingReport.splitCoverage")}><table className={styles.table}>
      <caption className="sr-only">{t("speakingReport.splitCoverage")}</caption>
      <thead><tr><th scope="col">{t("speakingReport.split")}</th><th scope="col">{t("speakingReport.samples")}</th><th scope="col">{t("speakingReport.pairs")}</th><th scope="col">{t("speakingReport.coverage")}</th></tr></thead>
      <tbody>{Object.entries(summary.split_metrics).map(([split, value]) => <tr key={split}><th scope="row">{split}</th><td>{value.eligible_samples}</td><td>{value.criteria.overall?.count ?? 0} / {value.criteria.overall?.total_count ?? 0}</td><td>{reportNumber(value.criteria.overall?.coverage_rate, true)}</td></tr>)}</tbody>
    </table></ReportTable>}
  </details>;
}
