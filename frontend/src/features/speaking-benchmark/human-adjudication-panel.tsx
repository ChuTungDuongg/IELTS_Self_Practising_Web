"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api/speaking-benchmark-human";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality/quality.module.css";

interface HumanAdjudicationPanelProps {
  sampleId: string;
  reviewRevision: number;
  onSampleUpdated?: () => void;
  onDirty?: (dirty: boolean) => void;
}

export function HumanAdjudicationPanel({
  sampleId,
  reviewRevision,
  onSampleUpdated,
  onDirty,
}: HumanAdjudicationPanelProps) {
  const { t } = useTranslation();
  const [raters, setRaters] = useState<api.HumanRater[]>([]);
  const [assignments, setAssignments] = useState<api.RaterAssignment[]>([]);
  const [assessments, setAssessments] = useState<api.HumanAssessment[]>([]);
  const [adjudications, setAdjudications] = useState<api.HumanAdjudication[]>([]);
  const [agreement, setAgreement] = useState<api.HumanAgreement | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Rater creation modal/form state
  const [showCreateRater, setShowCreateRater] = useState(false);
  const [raterKind, setRaterKind] = useState<"INTERNAL" | "EXTERNAL">("EXTERNAL");
  const [raterName, setRaterName] = useState("");
  const [externalKey, setExternalKey] = useState("");
  const [userId, setUserId] = useState("");

  // Assignment selection
  const [selectedRaterId, setSelectedRaterId] = useState("");

  // External assessment modal/form state
  const [showExternalForm, setShowExternalForm] = useState(false);
  const [externalAssignmentId, setExternalAssignmentId] = useState("");
  const [extBands, setExtBands] = useState<Record<string, number | null>>({
    fc: null,
    lr: null,
    gra: null,
    pr: null,
    overall: null,
  });
  const [extComments, setExtComments] = useState({
    fc: "",
    lr: "",
    gra: "",
    pr: "",
    overall: "",
  });
  const [extSourceRef, setExtSourceRef] = useState("");
  const [extProvenance, setExtProvenance] = useState<
    "external_verified_report" | "external_unverified"
  >("external_verified_report");
  const [extAttestation, setExtAttestation] = useState(false);

  // Adjudication form state
  const [adjAssessmentIds, setAdjAssessmentIds] = useState<string[]>([]);
  const [adjBands, setAdjBands] = useState<Record<string, number | null>>({
    fc: null,
    lr: null,
    gra: null,
    pr: null,
    overall: null,
  });
  const [adjRationale, setAdjRationale] = useState("");

  useEffect(() => { onDirty?.(showCreateRater || showExternalForm || Boolean(adjRationale.trim()) || adjAssessmentIds.length > 0); }, [showCreateRater, showExternalForm, adjRationale, adjAssessmentIds, onDirty]);
  const refresh = useCallback(async () => {
    if (!reviewRevision) return;
    setLoading(true);
    try {
      const [ratersData, assignmentsData, assessmentsData, adjudicationsData] =
        await Promise.all([
          api.listRaters(),
          api.listAssignments(sampleId),
          api.listAssessments(sampleId, reviewRevision),
          api.listAdjudications(sampleId, reviewRevision),
        ]);
      setRaters(ratersData.items);
      setAssignments(assignmentsData.items);
      setAssessments(assessmentsData.items);
      setAdjudications(adjudicationsData.items);

      if (assessmentsData.items.length >= 2) {
        try {
          const agree = await api.humanAgreement(sampleId, reviewRevision);
          setAgreement(agree);
        } catch {
          setAgreement(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sampleId, reviewRevision]);

  useEffect(() => {
    void Promise.resolve().then(refresh);
  }, [refresh]);

  const handleCreateRater = async () => {
    if (!raterName.trim()) return;
    setLoading(true);
    setError("");
    try {
      await api.createRater({
        kind: raterKind,
        display_name: raterName.trim(),
        ...(raterKind === "EXTERNAL" ? { external_key: externalKey.trim() } : { user_id: userId.trim() }),
      });
      setShowCreateRater(false);
      setRaterName("");
      setExternalKey("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleAssignRater = async () => {
    if (!selectedRaterId) return;
    setLoading(true);
    setError("");
    try {
      await api.createAssignment(sampleId, selectedRaterId, reviewRevision);
      setSelectedRaterId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeAssignment = async (assignment: api.RaterAssignment) => {
    setLoading(true);
    setError("");
    try {
      await api.revokeAssignment(sampleId, assignment);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitExternal = async () => {
    if (!externalAssignmentId || !extAttestation) return;
    setLoading(true);
    setError("");
    try {
      await api.submitExternalAssessment(sampleId, externalAssignmentId, {
        expected_revision: Math.max(0, ...assessments.filter(a => a.assignment_id === externalAssignmentId).map(a => a.revision)),
        bands: {
          fc: extBands.fc,
          lr: extBands.lr,
          gra: extBands.gra,
          pr: extBands.pr,
          overall: extBands.overall,
        },
        comments: extComments,
        independently_performed: extAttestation,
        provenance: extProvenance,
        source_reference: extSourceRef.trim(),
      });
      setShowExternalForm(false);
      await refresh();
      onSampleUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleAdjudicate = async () => {
    if (adjAssessmentIds.length === 0 || !adjRationale.trim()) return;
    setLoading(true);
    setError("");
    try {
      await api.adjudicate(sampleId, {
        review_revision: reviewRevision,
        expected_revision: Math.max(0, ...adjudications.map(a => a.revision)),
        assessment_ids: adjAssessmentIds,
        bands: {
          fc: adjBands.fc,
          lr: adjBands.lr,
          gra: adjBands.gra,
          pr: adjBands.pr,
          overall: adjBands.overall,
        },
        rationale: adjRationale.trim(),
        policy_version: "human-adjudication-v1",
      });
      setAdjRationale("");
      setAdjAssessmentIds([]);
      await refresh();
      onSampleUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.stack}>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}

      {/* Rater Management and Assignment Section */}
      <section className={styles.panel}>
        <div className={styles.cardHeader}>
          <h2>{t("speakingHuman.assignments")}</h2>
          <button
            className="btn btn-secondary"
            onClick={() => setShowCreateRater((v) => !v)}
          >
            {t("speakingHuman.createRater")}
          </button>
        </div>

        {showCreateRater && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <h3 className={styles.cardTitle}>{t("speakingHuman.createRater")}</h3>
            <div className={styles.form}>
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                <label style={{ flex: "0 0 160px" }}>
                  {t("speakingHuman.raterKind")}
                  <select
                    className="field"
                    value={raterKind}
                    onChange={(e) =>
                      setRaterKind(e.target.value as "INTERNAL" | "EXTERNAL")
                    }
                  >
                    <option value="EXTERNAL">{t("speakingHuman.external")}</option>
                    <option value="INTERNAL">{t("speakingHuman.internal")}</option>
                  </select>
                </label>

                <label style={{ flex: "1 1 200px" }}>
                  {t("speakingHuman.displayName")}
                  <input
                    type="text"
                    className="field"
                    value={raterName}
                    onChange={(e) => setRaterName(e.target.value)}
                    placeholder="e.g. Examiner Jane Doe"
                  />
                </label>

                {raterKind === "INTERNAL" && <label>{t("speakingHuman.userId")}<input className="field" value={userId} onChange={e => setUserId(e.target.value)} /></label>}
                {raterKind === "EXTERNAL" && (
                  <label style={{ flex: "1 1 200px" }}>
                    {t("speakingHuman.externalKey")}
                    <input
                      type="text"
                      className="field"
                      value={externalKey}
                      onChange={(e) => setExternalKey(e.target.value)}
                      placeholder="e.g. BC-TRF-EXAM-09"
                    />
                  </label>
                )}
              </div>

              <div className={styles.actions}>
                <button
                  className="btn btn-primary"
                  disabled={loading || !raterName.trim()}
                  onClick={() => void handleCreateRater()}
                >
                  {t("speakingHuman.createRater")}
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowCreateRater(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className={styles.toolbar}>
          <label style={{ flex: "1 1 240px" }}>
            {t("speakingHuman.assign")}
            <select
              className="field"
              value={selectedRaterId}
              onChange={(e) => setSelectedRaterId(e.target.value)}
              disabled={loading}
            >
              <option value="">-- Select Rater --</option>
              {raters.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.display_name} ({r.kind})
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn btn-primary"
            disabled={loading || !selectedRaterId}
            onClick={() => void handleAssignRater()}
          >
            {t("speakingHuman.assign")}
          </button>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Rater</th>
                <th>Status</th>
                <th>Assigned At</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {assignments.length === 0 ? (
                <tr>
                  <td colSpan={4} className={styles.muted}>
                    No rater assignments.
                  </td>
                </tr>
              ) : (
                assignments.map((a) => {
                  const rater = raters.find((r) => r.id === a.rater_id);
                  const isRevoked = Boolean(a.revoked_at);
                  return (
                    <tr key={a.id}>
                      <td>
                        <strong>{rater?.display_name ?? a.rater_id}</strong>
                        <div className={styles.muted}>Kind: {rater?.kind}</div>
                      </td>
                      <td>
                        <span
                          className={`${styles.badge} ${
                            isRevoked ? styles.badgeBlocked : styles.badgeReady
                          }`}
                        >
                          {isRevoked
                            ? t("speakingHuman.revoked")
                            : t("speakingHuman.active")}
                        </span>
                      </td>
                      <td>{new Date(a.created_at).toLocaleString()}</td>
                      <td>
                        {!isRevoked && (
                          <button
                            className="btn btn-ghost"
                            style={{ minHeight: "32px", padding: "4px 8px" }}
                            disabled={loading}
                            onClick={() => void handleRevokeAssignment(a)}
                          >
                            {t("speakingHuman.revoke")}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Submitted Assessments Section */}
      <section className={styles.panel}>
        <div className={styles.cardHeader}>
          <h2>
            {t("speakingHuman.assessments")} ({assessments.length})
          </h2>
          <button
            className="btn btn-secondary"
            onClick={() => setShowExternalForm((v) => !v)}
          >
            {t("speakingHuman.addExternal")}
          </button>
        </div>

        {showExternalForm && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <h3 className={styles.cardTitle}>{t("speakingHuman.addExternal")}</h3>
            <div className={styles.form}>
              <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                <label style={{ flex: "1 1 200px" }}>
                  Rater Assignment
                  <select
                    className="field"
                    value={externalAssignmentId}
                    onChange={(e) => setExternalAssignmentId(e.target.value)}
                  >
                    <option value="">-- Select Assignment --</option>
                    {assignments
                      .filter((a) => !a.revoked_at && a.review_revision === reviewRevision && raters.find(r => r.id === a.rater_id)?.kind === "EXTERNAL")
                      .map((a) => {
                        const r = raters.find((r) => r.id === a.rater_id);
                        return (
                          <option key={a.id} value={a.id}>
                            {r?.display_name ?? a.id}
                          </option>
                        );
                      })}
                  </select>
                </label>

                <label style={{ flex: "1 1 200px" }}>
                  {t("speakingHuman.provenance")}
                  <select
                    className="field"
                    value={extProvenance}
                    onChange={(e) =>
                      setExtProvenance(
                        e.target.value as
                          | "external_verified_report"
                          | "external_unverified"
                      )
                    }
                  >
                    <option value="external_verified_report">
                      {t("speakingHuman.verifiedReport")}
                    </option>
                    <option value="external_unverified">
                      {t("speakingHuman.unverified")}
                    </option>
                  </select>
                </label>

                <label style={{ flex: "1 1 200px" }}>
                  {t("speakingHuman.sourceRef")}
                  <input
                    type="text"
                    className="field"
                    value={extSourceRef}
                    onChange={(e) => setExtSourceRef(e.target.value)}
                    placeholder="e.g. TRF 123456"
                  />
                </label>
              </div>

              <div className={styles.scoreGrid}>
                {(["fc", "lr", "gra", "pr", "overall"] as const).map((crit) => (
                  <div key={crit} className={styles.scoreField}>
                    <label>{crit.toUpperCase()}</label>
                    <input
                      type="number"
                      step={0.5}
                      min={0}
                      max={9}
                      className="field"
                      value={extBands[crit] ?? ""}
                      onChange={(e) =>
                        setExtBands({
                          ...extBands,
                          [crit]: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                    />
                  </div>
                ))}
              </div>

              <div className={styles.commentsGrid}>
                {(["fc", "lr", "gra", "pr", "overall"] as const).map((crit) => (
                  <div
                    key={crit}
                    className={`${styles.commentField} ${
                      crit === "overall" ? styles.wide : ""
                    }`}
                  >
                    <label>{crit.toUpperCase()} Comment</label>
                    <textarea
                      className="field"
                      value={extComments[crit]}
                      onChange={(e) =>
                        setExtComments({
                          ...extComments,
                          [crit]: e.target.value,
                        })
                      }
                    />
                  </div>
                ))}
              </div>

              <div className={styles.check}>
                <input
                  type="checkbox"
                  id="extAttest"
                  checked={extAttestation}
                  onChange={(e) => setExtAttestation(e.target.checked)}
                />
                <label htmlFor="extAttest">
                  {t("speakingHuman.attestation")}
                </label>
              </div>

              <div className={styles.actions}>
                <button
                  className="btn btn-primary"
                  disabled={
                    loading || !externalAssignmentId || !extAttestation
                  }
                  onClick={() => void handleSubmitExternal()}
                >
                  Save Assessment
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowExternalForm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Rater</th>
                <th>FC</th>
                <th>LR</th>
                <th>GRA</th>
                <th>PR</th>
                <th>Overall</th>
                <th>Provenance</th>
                <th>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {assessments.length === 0 ? (
                <tr>
                  <td colSpan={8} className={styles.muted}>
                    {t("speakingHuman.noAssessments")}
                  </td>
                </tr>
              ) : (
                assessments.map((ass) => {
                  const rater = raters.find((r) => r.id === ass.rater_id);
                  return (
                    <tr key={ass.id}>
                      <td>
                        <strong>{rater?.display_name ?? ass.rater_id}</strong>
                        <div className={styles.muted}>{ass.source_reference}</div>
                      </td>
                      <td>{ass.bands.fc ?? "-"}</td>
                      <td>{ass.bands.lr ?? "-"}</td>
                      <td>{ass.bands.gra ?? "-"}</td>
                      <td>{ass.bands.pr ?? "-"}</td>
                      <td>
                        <strong>{ass.bands.overall ?? "-"}</strong>
                      </td>
                      <td>
                        <span
                          className={`${styles.badge} ${
                            ass.eligible
                              ? styles.badgeReady
                              : styles.badgeNeedsReview
                          }`}
                        >
                          {ass.provenance}
                        </span>
                      </td>
                      <td>{new Date(ass.submitted_at).toLocaleDateString()}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Inter-Rater Agreement Summary Card */}
      {agreement && (
        <section className={styles.panel}>
          <h2>{t("speakingHuman.agreement")}</h2>
          <div className={styles.counters}>
            <div className={styles.counterItem}>
              <div className={styles.counterLabel}>
                {t("speakingHuman.independentRaters")}
              </div>
              <div className={styles.counterValue}>
                {agreement.independent_raters}
              </div>
            </div>
            <div className={styles.counterItem}>
              <div className={styles.counterLabel}>
                {t("speakingHuman.independentSamples")}
              </div>
              <div className={styles.counterValue}>
                {agreement.independent_samples}
              </div>
            </div>
          </div>

          {agreement.limitations.length > 0 && (
            <div className={styles.noticeWarning}>
              <strong>{t("speakingHuman.limitations")}:</strong>
              <ul>
                {agreement.limitations.map((lim, i) => (
                  <li key={i}>{lim}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {/* Final Adjudication Section */}
      <section className={styles.panel}>
        <h2>{t("speakingHuman.adjudication")}</h2>
        <p className={styles.muted}>{t("speakingHuman.adjudicationPolicy")}</p>

        {adjudications.length > 0 && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <div className={styles.cardHeader}>
              <h3 className={styles.cardTitle}>Current Adjudicated Label</h3>
              <span className={styles.badgeReady + " " + styles.badge}>
                Revision {adjudications[0].revision}
              </span>
            </div>
            <div className={styles.scoreGrid}>
              <div>
                <strong>FC:</strong> {adjudications[0].bands.fc}
              </div>
              <div>
                <strong>LR:</strong> {adjudications[0].bands.lr}
              </div>
              <div>
                <strong>GRA:</strong> {adjudications[0].bands.gra}
              </div>
              <div>
                <strong>PR:</strong> {adjudications[0].bands.pr}
              </div>
              <div>
                <strong>Overall:</strong> {adjudications[0].bands.overall}
              </div>
            </div>
            <p style={{ marginTop: "8px" }}>
              <strong>Rationale:</strong> {adjudications[0].rationale}
            </p>
            <div className={styles.muted} style={{ fontSize: "12px" }}>
              {t("speakingHuman.adjudicatedAt")}:{" "}
              {new Date(adjudications[0].adjudicated_at).toLocaleString()}
            </div>
          </div>
        )}

        <div className={styles.form}>
          <div>
            <label>
              <strong>{t("speakingHuman.selectAssessments")}</strong>
            </label>
            <div style={{ display: "grid", gap: "8px", marginTop: "8px" }}>
              {assessments.map((ass) => {
                const rater = raters.find((r) => r.id === ass.rater_id);
                const isSelected = adjAssessmentIds.includes(ass.id);
                return (
                  <div key={ass.id} className={styles.check}>
                    <input
                      type="checkbox"
                      id={`adj-${ass.id}`}
                      checked={isSelected}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setAdjAssessmentIds([...adjAssessmentIds, ass.id]);
                        } else {
                          setAdjAssessmentIds(
                            adjAssessmentIds.filter((id) => id !== ass.id)
                          );
                        }
                      }}
                    />
                    <label htmlFor={`adj-${ass.id}`}>
                      {rater?.display_name ?? ass.rater_id} — Overall:{" "}
                      {ass.bands.overall ?? "-"} (FC: {ass.bands.fc}, LR:{" "}
                      {ass.bands.lr}, GRA: {ass.bands.gra}, PR: {ass.bands.pr})
                    </label>
                  </div>
                );
              })}
            </div>
          </div>

          <div className={styles.scoreGrid}>
            {(["fc", "lr", "gra", "pr", "overall"] as const).map((crit) => (
              <div key={crit} className={styles.scoreField}>
                <label>ADJUDICATED {crit.toUpperCase()}</label>
                <input
                  type="number"
                  step={0.5}
                  min={0}
                  max={9}
                  className="field"
                  value={adjBands[crit] ?? ""}
                  onChange={(e) =>
                    setAdjBands({
                      ...adjBands,
                      [crit]: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </div>
            ))}
          </div>

          <label>
            {t("speakingHuman.rationale")}
            <textarea
              className="field"
              value={adjRationale}
              onChange={(e) => setAdjRationale(e.target.value)}
              placeholder="State the justification for this final consensus or adjudication..."
            />
          </label>

          <div className={styles.actions}>
            <button
              className="btn btn-primary"
              disabled={
                loading ||
                adjAssessmentIds.length === 0 ||
                !adjRationale.trim()
              }
              onClick={() => void handleAdjudicate()}
            >
              {t("speakingHuman.adjudicateAction")}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
