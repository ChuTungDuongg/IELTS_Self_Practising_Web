"use client";

import { LabNavigation } from "../lab-navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-quality";
import { listSpeakingSamples } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality.module.css";

export function QualityDashboard() {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [severity, setSeverity] = useState("ALL");
  const [report, setReport] = useState<api.QualityReport | null>(null);
  const [snapshots, setSnapshots] = useState<api.QualitySnapshot[]>([]);

  // Policy options
  const [requireHuman, setRequireHuman] = useState(true);
  const [requireAdjudication, setRequireAdjudication] = useState(false);
  const [requireSourceBound, setRequireSourceBound] = useState(true);
  const [requireAsrRefs, setRequireAsrRefs] = useState(false);
  const [requireAllParts, setRequireAllParts] = useState(true);
  const [minCandidates, setMinCandidates] = useState(10);
  const [labelKind, setLabelKind] = useState<"LEGACY" | "INDEPENDENT" | "ADJUDICATED">("ADJUDICATED");

  const loadSnapshots = useCallback(async () => {
    try {
      const list = await api.qualitySnapshots();
      setSnapshots(list);
    } catch {
      // Ignored
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadSnapshots);
  }, [loadSnapshots]);

  const handleEvaluate = async () => {
    setLoading(true);
    setError("");
    try {
      const samplesRes = await listSpeakingSamples(0);
      const cohort = samplesRes.items
        .filter((s) => s.review_revision && s.status === "APPROVED")
        .map((s) => ({
          sample_id: s.id,
          review_revision: s.review_revision!,
        }));

      const req: api.QualityRequest = {
        cohort,
        label_selection: { kind: labelKind },
        policy: {
          protocol: "speaking-dataset-quality-v1",
          require_human_label: requireHuman,
          require_adjudication: requireAdjudication,
          require_source_bound_labels: requireSourceBound,
          require_asr_references: requireAsrRefs,
          require_all_parts: requireAllParts,
          minimum_independent_candidates: minCandidates,
        },
      };

      const res = await api.evaluateQuality(req);
      setReport(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSnapshot = async () => {
    if (!report) return;
    setLoading(true);
    setError("");
    try {
      const samplesRes = await listSpeakingSamples(0);
      const cohort = samplesRes.items
        .filter((s) => s.review_revision && s.status === "APPROVED")
        .map((s) => ({
          sample_id: s.id,
          review_revision: s.review_revision!,
        }));

      const req: api.QualityRequest = {
        cohort,
        label_selection: { kind: labelKind },
        policy: {
          protocol: "speaking-dataset-quality-v1",
          require_human_label: requireHuman,
          require_adjudication: requireAdjudication,
          require_source_bound_labels: requireSourceBound,
          require_asr_references: requireAsrRefs,
          require_all_parts: requireAllParts,
          minimum_independent_candidates: minCandidates,
        },
      };

      await api.saveQualitySnapshot(req);
      await loadSnapshots();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const statusBadgeClass =
    report?.status === "READY"
      ? styles.badgeReady
      : report?.status === "BLOCKED"
      ? styles.badgeBlocked
      : report?.status === "NEEDS_REVIEW"
      ? styles.badgeNeedsReview
      : styles.badgeInsufficient;

  return (
    <div className={styles.stack}>
      <PageHeading
        eyebrow={t("admin.administration")}
        title={t("speakingQuality.title")}
        description={t("speakingQuality.description")}
      />
      <LabNavigation current="quality" tool="quality" />

      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}

      <section className={styles.panel} aria-busy={loading}>
        {!report && <><h2>{t("speakingUx.qualityResults")}</h2><p className={styles.muted}>{t("speakingUx.qualityEmpty")}</p></>}
          <div className={styles.actions}>
            <button
              className="btn btn-primary"
              disabled={loading}
              onClick={() => void handleEvaluate()}
            >
              {t("speakingQuality.evaluate")}
            </button>
            {report && (
              <button
                className="btn btn-secondary"
                disabled={loading}
                onClick={() => void handleSnapshot()}
              >
                {t("speakingQuality.snapshot")}
              </button>
            )}
          </div>
        <p className={styles.muted}>{t("speakingUx.firstPageScope")}</p>
      </section>
      {/* Quality Audit Report Results */}
      {report && (
        <section className={styles.panel}>
          <div className={styles.cardHeader}>
            <h2>{t("speakingUx.qualityResults")}</h2>
            <span className={`${styles.badge} ${statusBadgeClass}`}>
              {report.status}
            </span>
          </div>

          <div className={styles.counters}>
            <div className={styles.counterItem}>
              <div className={styles.counterLabel}>
                {t("speakingQuality.eligibleSamples")}
              </div>
              <div className={styles.counterValue}>{report.eligible_samples}</div>
            </div>
            <div className={styles.counterItem}>
              <div className={styles.counterLabel}>
                {t("speakingQuality.ineligibleSamples")}
              </div>
              <div className={styles.counterValue}>
                {report.ineligible_samples}
              </div>
            </div>
            <div className={styles.counterItem}>
              <div className={styles.counterLabel}>
                {t("speakingQuality.independentCandidates")}
              </div>
              <div className={styles.counterValue}>
                {report.independent_candidates}
              </div>
            </div>
          </div>

          <h3 style={{ marginTop: "24px" }}>
            {t("speakingQuality.issues")} ({report.issues.length})
          </h3>

          <label className={styles.form}>{t("speakingUx.issueFilter")}
            <select className="field" value={severity} onChange={event => setSeverity(event.target.value)}>
              <option value="ALL">{t("speakingUx.allIssues")}</option>
              {(["BLOCKED", "NEEDS_REVIEW", "INSUFFICIENT_DATA"] as const).map(value => <option key={value}>{value}</option>)}
            </select>
          </label>
          {report.issues.length === 0 ? (
            <p className={styles.muted}>{t("speakingQuality.noIssues")}</p>
          ) : (
            <div className={styles.tableWrap}>
              {severity !== "ALL" && !report.issues.some(issue => issue.severity === severity) && <p role="status">{t("speakingUx.noMatchingIssues")}</p>}
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("speakingQuality.severity")}</th>
                    <th scope="col">{t("speakingQuality.code")}</th>
                    <th scope="col">{t("speakingQuality.artifact")}</th>
                    <th scope="col">{t("speakingQuality.remediation")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.issues.filter(issue => severity === "ALL" || issue.severity === severity).map((issue, idx) => {
                    const badgeClass =
                      issue.severity === "BLOCKED"
                        ? styles.badgeBlocked
                        : issue.severity === "NEEDS_REVIEW"
                        ? styles.badgeNeedsReview
                        : styles.badgeInsufficient;
                    return (
                      <tr key={idx}>
                        <td>
                          <span className={`${styles.badge} ${badgeClass}`}>
                            {issue.severity}
                          </span>
                        </td>
                        <td>
                          <details><summary>{t("speakingUx.details")}</summary><code>{issue.code}</code></details>
                        </td>
                        <td>
                          <div>{issue.artifact}</div>
                          <div className={styles.muted} style={{ fontSize: "12px" }}>
                            {issue.artifact_id}
                          </div>
                        </td>
                        <td>{issue.remediation}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Quality Policy Configuration */}
      <details className={styles.panel}>
        <summary>{t("speakingUx.policyHelp")}</summary>
        <p className={styles.muted}>{t("speakingQuality.protocol")}</p>

        <div className={styles.form} style={{ marginTop: "16px" }}>
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
            <label style={{ flex: "1 1 200px" }}>
              {t("speakingQuality.labelSelection")}
              <select
                className="field"
                value={labelKind}
                onChange={(e) =>
                  setLabelKind(
                    e.target.value as "LEGACY" | "INDEPENDENT" | "ADJUDICATED"
                  )
                }
              >
                <option value="LEGACY">{t("speakingUx.legacyLabel")}</option>
                <option value="INDEPENDENT">{t("speakingUx.independentLabel")}</option>
                <option value="ADJUDICATED">{t("speakingUx.adjudicatedLabel")}</option>
              </select>
            </label>

            <label style={{ flex: "1 1 200px" }}>
              {t("speakingQuality.minCandidates")}
              <input
                type="number"
                min={1}
                max={1000}
                className="field"
                value={minCandidates}
                onChange={(e) => setMinCandidates(Number(e.target.value))}
              />
            </label>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "8px",
            }}
          >
            <div className={styles.check}>
              <input
                type="checkbox"
                id="qReqHuman"
                checked={requireHuman}
                onChange={(e) => setRequireHuman(e.target.checked)}
              />
              <label htmlFor="qReqHuman">{t("speakingQuality.requireHuman")}</label>
            </div>

            <div className={styles.check}>
              <input
                type="checkbox"
                id="qReqAdj"
                checked={requireAdjudication}
                onChange={(e) => setRequireAdjudication(e.target.checked)}
              />
              <label htmlFor="qReqAdj">
                {t("speakingQuality.requireAdjudication")}
              </label>
            </div>

            <div className={styles.check}>
              <input
                type="checkbox"
                id="qReqSource"
                checked={requireSourceBound}
                onChange={(e) => setRequireSourceBound(e.target.checked)}
              />
              <label htmlFor="qReqSource">
                {t("speakingQuality.requireSourceBound")}
              </label>
            </div>

            <div className={styles.check}>
              <input
                type="checkbox"
                id="qReqAsr"
                checked={requireAsrRefs}
                onChange={(e) => setRequireAsrRefs(e.target.checked)}
              />
              <label htmlFor="qReqAsr">
                {t("speakingQuality.requireAsrRefs")}
              </label>
            </div>

            <div className={styles.check}>
              <input
                type="checkbox"
                id="qReqParts"
                checked={requireAllParts}
                onChange={(e) => setRequireAllParts(e.target.checked)}
              />
              <label htmlFor="qReqParts">
                {t("speakingQuality.requireAllParts")}
              </label>
            </div>
          </div>


        </div>
      </details>

      {/* Quality Snapshots History */}
      <details className={styles.panel}>
        <summary>{t("speakingQuality.snapshots")} ({snapshots.length})</summary>
        {snapshots.length === 0 ? (
          <p className={styles.muted}>{t("speakingUx.snapshotEmpty")}</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">{t("speakingUx.snapshotId")}</th>
                  <th scope="col">{t("speakingUx.fingerprint")}</th>
                  <th scope="col">{t("speakingUx.createdAt")}</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((snap) => (
                  <tr key={snap.id}>
                    <td>
                      <code>{snap.id}</code>
                    </td>
                    <td>
                      <code style={{ fontSize: "12px" }}>
                        {snap.fingerprint.substring(0, 16)}…
                      </code>
                    </td>
                    <td>{new Date(snap.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </div>
  );
}
