"use client";

import { LabNavigation } from "../lab-navigation";
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
  const [inspectionConsent, setInspectionConsent] = useState(false);

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
      setSelectedSuite(await api.getSuite(suite.id, inspectionConsent));
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
      />
      <LabNavigation current="quality" tool="suites" />

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
            className="btn btn-secondary"
            aria-expanded={showCreate}
            onClick={() => setShowCreate((v) => !v)}
          >
            {t("speakingSuites.new")}
          </button>
        </div>

        {showCreate && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <p className={styles.muted}>{t("speakingUx.suiteHelp")}</p>
            <p className={styles.muted}>{t("speakingUx.firstPageScope")}</p>
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
                    <option value="LEGACY">{t("speakingUx.legacyLabel")}</option>
                    <option value="INDEPENDENT">{t("speakingUx.independentLabel")}</option>
                    <option value="ADJUDICATED">{t("speakingUx.adjudicatedLabel")}</option>
                  </select>
                </label>
              </div>

              <label>
                {t("speakingSuites.suiteDescription")}
                <textarea
                  className="field"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>

              {/* Sample Selector */}
              <div>
                <label>
                  <strong>{t("speakingUx.cohort", { count: selectedSampleIds.length })}</strong>
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
                  {t("speakingUx.createSuite")}
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setShowCreate(false)}
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>
        )}

        <p className={styles.muted}>{t("speakingSuites.holdoutWarning")}</p>
        <label className={styles.check}><input type="checkbox" checked={inspectionConsent} onChange={event => setInspectionConsent(event.target.checked)} />{t("speakingUx.inspectionConsent")}</label>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">{t("speakingSuites.name")}</th>
                <th scope="col">{t("speakingUx.revision")}</th>
                <th scope="col">{t("speakingSuites.fingerprint")}</th>
                <th scope="col">{t("speakingSuites.frozenAt")}</th>
                <th scope="col">{t("speakingUx.action")}</th>
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
                        {t("speakingUx.inspect")}
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
              {t("speakingUx.close")}
            </button>
          </div>

          <p className={styles.muted}>{selectedSuite.description}</p>
          <details><summary>{t("speakingUx.frozenBinding")}</summary>
            <p>{t("speakingUx.fingerprint")}: <code>{selectedSuite.fingerprint}</code></p>
            <pre>{JSON.stringify(selectedSuite.configuration, null, 2)}</pre>
          </details>

          <h3 style={{ marginTop: "20px" }}>{t("speakingSuites.audits")}</h3>
          {audits.length === 0 ? (
            <p className={styles.muted}>{t("speakingSuites.noAudits")}</p>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">{t("speakingUx.auditId")}</th>
                    <th scope="col">{t("speakingUx.action")}</th>
                    <th scope="col">{t("speakingUx.timestamp")}</th>
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
