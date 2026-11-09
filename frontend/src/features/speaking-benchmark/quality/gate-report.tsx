"use client";

import * as api from "@/lib/api/speaking-benchmark-quality";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality.module.css";

export function gateStatusClass(status: string) {
  return status === "PASS" ? styles.badgePass : status === "FAIL" ? styles.badgeFail : status === "INCONCLUSIVE" ? styles.badgeInconclusive : styles.badgeInvalid;
}

const numeric = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const format = (value: unknown, signed = false) => numeric(value) ? `${signed && value > 0 ? "+" : ""}${value.toFixed(4)}` : "—";
const records = (value: unknown): Record<string, unknown>[] => Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null) : [];
const messages = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

export function GateReport({ selectedReport }: { selectedReport: api.RegressionReport }) {
  const { t } = useTranslation();
  const evidence = selectedReport.report;
  const metrics = records(evidence.metrics);
  const reasons = messages(evidence.reasons);
  const limitations = messages(evidence.limitations);
  return <div className={styles.report}>
    <div className={styles.cardHeader}>
      <h3>{t("speakingGates.report")}</h3>
      <span className={`${styles.badge} ${gateStatusClass(selectedReport.status)}`}>{selectedReport.status}</span>
      <div className={styles.actions}>
        <a className="btn btn-secondary" href={api.regressionExportUrl(selectedReport.id, "csv")} download>{t("speakingGates.exportCsv")}</a>
        <a className="btn btn-secondary" href={api.regressionExportUrl(selectedReport.id, "json")} download>{t("speakingGates.exportJson")}</a>
      </div>
    </div>
    <dl className={styles.counters}>
      {([
        ["speakingUx.matchedSamples", evidence.matched_samples],
        ["speakingUx.independentCandidates", evidence.matched_independent_candidates],
        ["speakingGates.unknownBilling", evidence.candidate_unknown_billing_requests],
      ] as const).map(([label, value]) => <div key={label} className={styles.counterItem}><dt className={styles.counterLabel}>{t(label)}</dt><dd className={styles.counterValue}>{numeric(value) ? value : "—"}</dd></div>)}
    </dl>
    {reasons.length > 0 && <div className={styles.noticeWarning}>
      <h4>{t("speakingUx.releaseReasons")}</h4>
      <ul>{reasons.map(reason => <li key={reason}>{reason === "INSUFFICIENT_MATCHED_INDEPENDENT_CANDIDATES" ? t("speakingUx.needCandidates") : t("speakingUx.reviewReason")} <code>{reason}</code></li>)}</ul>
    </div>}
    <p className={styles.muted}>{t("speakingUx.releaseHelp")}</p>
    <div className={styles.tableWrap}><table className={styles.table}>
      <thead><tr><th scope="col">{t("speakingGates.metric")}</th><th scope="col" className={styles.numeric}>{t("speakingUx.baseline")}</th><th scope="col" className={styles.numeric}>{t("speakingUx.candidate")}</th><th scope="col" className={styles.numeric}>{t("speakingGates.difference")}</th><th scope="col">{t("speakingUx.status")}</th></tr></thead>
      <tbody>{!metrics.length ? <tr><td colSpan={5}>{t("speakingUx.noMetrics")}</td></tr> : metrics.map(metric => <tr key={String(metric.metric)}>
        <th scope="row"><code>{String(metric.metric)}</code></th>
        <td className={styles.numeric}>{format(metric.baseline)}</td><td className={styles.numeric}>{format(metric.candidate)}</td><td className={styles.numeric}>{format(metric.difference, true)}</td>
        <td><span className={`${styles.badge} ${gateStatusClass(String(metric.status))}`}>{String(metric.status ?? "—")}</span></td>
      </tr>)}</tbody>
    </table></div>
    {limitations.length > 0 && <div className={styles.noticeWarning}><h4>{t("speakingUx.limitations")}</h4><ul>{limitations.map(message => <li key={message}><code>{message}</code></li>)}</ul></div>}
    <details className={styles.evidence}>
      <summary>{t("speakingUx.details")}</summary>
      <p>{t("speakingUx.reportId")}: <code>{selectedReport.id}</code></p>
      <p>{t("speakingUx.protocol")}: <code>{selectedReport.protocol}</code></p>
      <p>{t("speakingUx.fingerprint")}: <code>{selectedReport.fingerprint}</code></p>
      <div className={styles.tableWrap}><table className={styles.table}>
        <thead><tr><th scope="col">{t("speakingGates.metric")}</th><th scope="col">{t("speakingGates.relDifference")}</th><th scope="col">{t("speakingGates.maxRegression")}</th><th scope="col">{t("speakingGates.bootstrapCI")}</th></tr></thead>
        <tbody>{metrics.map(metric => {
          const paired = metric.paired as { ci95?: number[] | null } | undefined;
          const ci = paired?.ci95;
          return <tr key={String(metric.metric)}><th scope="row">{String(metric.metric)}</th><td>{numeric(metric.relative_difference) ? `${(metric.relative_difference * 100).toFixed(2)}%` : "—"}</td><td>{format(metric.tolerable_regression)}</td><td>{ci?.length === 2 ? `[${ci[0].toFixed(3)}, ${ci[1].toFixed(3)}]` : "—"}</td></tr>;
        })}</tbody>
      </table></div>
      <pre>{JSON.stringify(evidence, null, 2)}</pre>
    </details>
  </div>;
}
