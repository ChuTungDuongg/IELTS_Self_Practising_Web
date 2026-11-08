"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-quality";
import { listSpeakingSamples, type SpeakingSample } from "@/lib/api/speaking-benchmark";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality.module.css";

export function SuiteManager() {
  const { t } = useTranslation();
  const [suites, setSuites] = useState<api.EvaluationSuite[]>([]);
  const [samples, setSamples] = useState<SpeakingSample[]>([]);
  const [selectedSuite, setSelectedSuite] = useState<api.EvaluationSuite | null>(null);
  const [audits, setAudits] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  // Create form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [selectedSampleIds, setSelectedSampleIds] = useState<string[]>([]);
  const [labelKind, setLabelKind] = useState<"LEGACY" | "INDEPENDENT" | "ADJUDICATED">("ADJUDICATED");
  const [holdout, setHoldout] = useState(false);
  const [holdoutConsent, setHoldoutConsent] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [suitesList, samplesRes] = await Promise.all([
        api.listSuites(),
        listSpeakingSamples(0),
      ]);
      setSuites(suitesList);
      setSamples(samplesRes.items.filter((s) => s.review_revision && s.status === "APPROVED"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const handleSelectSuite = async (suite: api.EvaluationSuite) => {
    try {
      setSelectedSuite(await api.getSuite(suite.id, holdoutConsent));
      const auditLog = await api.suiteAudits(suite.id);
      setAudits(auditLog);
    } catch (err) {
      setError(String(err));
      setAudits([]);
    }
  };

  const handleCreateSuite = async () => {
    if (!name.trim() || selectedSampleIds.length === 0) return;
    if (holdout && !holdoutConsent) return;
    setLoading(true);
    setError("");
    try {
      const cohort = selectedSampleIds.map((id) => {
        const s = samples.find((x) => x.id === id);
        return {
          sample_id: id,
          review_revision: s?.review_revision ?? 1,
        };
      });

      const body = {
        name: name.trim(),
        description: description.trim(),
        expected_revision: 0,
        holdout_evaluation: holdout,
        cohort,
        label_selection: { kind: labelKind },
        policy: {
          protocol: "speaking-dataset-quality-v1" as const,
          require_human_label: true,
          require_adjudication: false,
          require_source_bound_labels: labelKind !== "LEGACY",
          require_asr_references: false,
          require_all_parts: true,
          minimum_independent_candidates: 10,
        },
      };

      const created = await api.createSuite(body);
      setShowCreate(false);
      setName("");
      setDescription("");
      setSelectedSampleIds([]);
      setHoldout(false);
      setHoldoutConsent(false);
      await load();
      setSelectedSuite(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.stack}>
      <PageHeading
        eyebrow={t("admin.administration")}
        title={t("speakingSuites.title")}
        description={t("speakingSuites.description")}
        action={
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark">
              {t("speakingLab.title")}
            </Link>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark/quality">
              {t("speakingLab.quality")}
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

      {/* Suites List & Create Button */}
      <section className={styles.panel}>
        <div className={styles.cardHeader}>
          <h2>{t("speakingSuites.title")} ({suites.length})</h2>
          <button
            className="btn btn-primary"
            onClick={() => setShowCreate((v) => !v)}
          >
            {t("speakingSuites.new")}
          </button>
        </div>

        {showCreate && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <h3 className={styles.cardTitle}>{t("speakingSuites.new")}</h3>
            <div className={styles.form}>
              <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                <label style={{ flex: "1 1 240px" }}>
                  {t("speakingSuites.name")}
                  <input
                    type="text"
                    className="field"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Production Speaking Benchmark Suite 2026-Q4"
                  />
                </label>

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
                    <option value="LEGACY">LEGACY</option>
                    <option value="INDEPENDENT">INDEPENDENT</option>
                    <option value="ADJUDICATED">ADJUDICATED</option>
                  </select>
                </label>
              </div>

              <label>
                {t("speakingSuites.suiteDescription")}
                <textarea
                  className="field"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the target evaluation purpose and cohort criteria..."
                />
              </label>

              {/* Sample Selector */}
              <div>
                <label>
                  <strong>Select Cohort Samples ({selectedSampleIds.length} selected)</strong>
                </label>
                <div
                  style={{
                    maxHeight: "200px",
                    overflowY: "auto",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    padding: "8px 12px",
                    marginTop: "6px",
                  }}
                >
                  {samples.map((s) => {
                    const checked = selectedSampleIds.includes(s.id);
                    return (
                      <div key={s.id} className={styles.check}>
                        <input
                          type="checkbox"
                          id={`s-${s.id}`}
                          checked={checked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedSampleIds([...selectedSampleIds, s.id]);
                            } else {
                              setSelectedSampleIds(
                                selectedSampleIds.filter((id) => id !== s.id)
                              );
                            }
                          }}
                        />
                        <label htmlFor={`s-${s.id}`}>
                          {s.code} ({s.split}) — {Math.round(s.duration_ms / 1000)}s — Rev{" "}
                          {s.review_revision}
                        </label>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Holdout Options & Warning */}
              <div className={styles.check}>
                <input
                  type="checkbox"
                  id="sHoldout"
                  checked={holdout}
                  onChange={(e) => setHoldout(e.target.checked)}
                />
                <label htmlFor="sHoldout">
                  <strong>{t("speakingSuites.holdoutEvaluation")}</strong>
                </label>
              </div>

              {holdout && (
                <div className={styles.noticeWarning}>
                  <strong>{t("speakingSuites.holdoutWarning")}</strong>
                  <div className={styles.check} style={{ marginTop: "8px" }}>
                    <input
                      type="checkbox"
                      id="sHoldoutConsent"
                      checked={holdoutConsent}
                      onChange={(e) => setHoldoutConsent(e.target.checked)}
                    />
                    <label htmlFor="sHoldoutConsent">
                      {t("speakingSuites.holdoutConsent")}
                    </label>
                  </div>
                </div>
              )}

              <div className={styles.actions}>
                <button
                  className="btn btn-primary"
                  disabled={
                    loading ||
                    !name.trim() ||
                    selectedSampleIds.length === 0 ||
                    (holdout && !holdoutConsent)
                  }
                  onClick={() => void handleCreateSuite()}
                >
                  Create Frozen Suite
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowCreate(false)}
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
                <th>{t("speakingSuites.name")}</th>
                <th>Revision</th>
                <th>{t("speakingSuites.fingerprint")}</th>
                <th>{t("speakingSuites.frozenAt")}</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {suites.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.muted}>
                    {t("speakingSuites.empty")}
                  </td>
                </tr>
              ) : (
                suites.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.name}</strong>
                      <div className={styles.muted}>{s.description}</div>
                    </td>
                    <td>Rev {s.revision}</td>
                    <td>
                      <code style={{ fontSize: "12px" }}>
                        {s.fingerprint.substring(0, 16)}…
                      </code>
                    </td>
                    <td>{new Date(s.frozen_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ minHeight: "32px", padding: "4px 10px" }}
                        onClick={() => void handleSelectSuite(s)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Selected Suite Inspection & Audit Log */}
      {selectedSuite && (
        <section className={styles.panel}>
          <div className={styles.cardHeader}>
            <h2>{selectedSuite.name} (Rev {selectedSuite.revision})</h2>
            <button
              className="btn btn-ghost"
              onClick={() => setSelectedSuite(null)}
            >
              Close
            </button>
          </div>

          <p className={styles.muted}>{selectedSuite.description}</p>
          <div className={styles.muted} style={{ marginTop: "6px" }}>
            <strong>Frozen Fingerprint:</strong> <code>{selectedSuite.fingerprint}</code>
          </div>

          <h3 style={{ marginTop: "20px" }}>{t("speakingSuites.audits")}</h3>
          {audits.length === 0 ? (
            <p className={styles.muted}>{t("speakingSuites.noAudits")}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Audit ID</th>
                    <th>Action</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {audits.map((a, i) => (
                    <tr key={i}>
                      <td><code>{String(a.id ?? i)}</code></td>
                      <td>{String(a.action ?? "HOLD_EVAL")}</td>
                      <td>{String(a.created_at ?? "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
