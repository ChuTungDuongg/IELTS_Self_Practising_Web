"use client";

import Link from "next/link";
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
        action={
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark">
              {t("speakingLab.title")}
            </Link>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark/suites">
              {t("speakingLab.suites")}
            </Link>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark/gates">
              {t("speakingLab.gates")}
            </Link>
          </div>
        }
      />

      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}

      {/* Quality Policy Configuration */}
      <section className={styles.panel}>
        <h2>{t("speakingQuality.policy")}</h2>
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
                <option value="LEGACY">LEGACY (P1 Human Labels)</option>
                <option value="INDEPENDENT">INDEPENDENT (Rater Assessments)</option>
                <option value="ADJUDICATED">ADJUDICATED (Consensus Labels)</option>
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
        </div>
      </section>

      {/* Quality Audit Report Results */}
      {report && (
        <section className={styles.panel}>
          <div className={styles.cardHeader}>
            <h2>Quality Audit Results</h2>
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

          {report.issues.length === 0 ? (
            <p className={styles.muted}>{t("speakingQuality.noIssues")}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t("speakingQuality.severity")}</th>
                    <th>{t("speakingQuality.code")}</th>
                    <th>{t("speakingQuality.artifact")}</th>
                    <th>{t("speakingQuality.remediation")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.issues.map((issue, idx) => {
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
                          <code>{issue.code}</code>
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

      {/* Quality Snapshots History */}
      <section className={styles.panel}>
        <h2>{t("speakingQuality.snapshots")} ({snapshots.length})</h2>
        {snapshots.length === 0 ? (
          <p className={styles.muted}>No quality snapshots recorded yet.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Snapshot ID</th>
                  <th>Fingerprint</th>
                  <th>Created At</th>
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
      </section>
    </div>
  );
}
