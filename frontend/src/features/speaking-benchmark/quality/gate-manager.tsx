"use client";

import { GateSourceSelector } from "./gate-source-selector";
import { GateReport } from "./gate-report";
import { LabNavigation } from "../lab-navigation";
import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-quality";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality.module.css";

export function GateManager() {
  const { t } = useTranslation();
  const [gates, setGates] = useState<api.RegressionGate[]>([]);
  const [suites, setSuites] = useState<api.EvaluationSuite[]>([]);
  const [selectedGate, setSelectedGate] = useState<api.RegressionGate | null>(null);
  const [reports, setReports] = useState<api.RegressionReport[]>([]);
  const [selectedReport, setSelectedReport] = useState<api.RegressionReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [minimumCandidates, setMinimumCandidates] = useState(10);
  const [predictionCoverage, setPredictionCoverage] = useState(1);
  const [referenceCoverage, setReferenceCoverage] = useState(1);
  const [comparison, setComparison] = useState<'CONFIGURATION' | 'LEXICAL_ASR'>('CONFIGURATION');
  const [holdoutConsent, setHoldoutConsent] = useState(false);

  // Create gate form state
  const [name, setName] = useState("");
  const [suiteId, setSuiteId] = useState("");
  const [baselineKind, setBaselineKind] = useState<"GRADING" | "EXPERIMENT">("GRADING");
  const [baselineFp, setBaselineFp] = useState("");
  const [baselineExpId, setBaselineExpId] = useState("");
  const [baselineVariantKey, setBaselineVariantKey] = useState("");

  const [candidateKind, setCandidateKind] = useState<"GRADING" | "EXPERIMENT">("GRADING");
  const [candidateFp, setCandidateFp] = useState("");
  const [candidateExpId, setCandidateExpId] = useState("");
  const [candidateVariantKey, setCandidateVariantKey] = useState("");

  const [thresholdMetric, setThresholdMetric] = useState<typeof api.metrics[number]>("wer");
  const [thresholdMax, setThresholdMax] = useState(0.0);
  const [thresholds, setThresholds] = useState<
    { metric: typeof api.metrics[number]; max_regression: number }[]
  >([{ metric: "wer", max_regression: 0.0 }]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [gatesList, suitesList] = await Promise.all([
        api.listGates(),
        api.listSuites(),
      ]);
      setGates(gatesList);
      setSuites(suitesList);
      if (suitesList.length > 0 && !suiteId) {
        setSuiteId(suitesList[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [suiteId]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const handleSelectGate = async (gate: api.RegressionGate) => {
    setSelectedGate(gate);
    setSelectedReport(null);
    try {
      const reps = await api.gateReports(gate.id);
      setReports(reps);
      if (reps.length > 0) {
        setSelectedReport(reps[0]);
      }
    } catch {
      setReports([]);
    }
  };

  const handleCreateGate = async () => {
    if (!name.trim() || !suiteId || thresholds.length === 0) return;
    setLoading(true);
    setError("");
    try {
      const baseline: api.PersistedSelection =
        baselineKind === "GRADING"
          ? { kind: "GRADING", configuration_fingerprint: baselineFp.trim() }
          : {
              kind: "EXPERIMENT",
              id: baselineExpId.trim(),
              variant_key: baselineVariantKey.trim(),
            };

      const candidate: api.PersistedSelection =
        candidateKind === "GRADING"
          ? { kind: "GRADING", configuration_fingerprint: candidateFp.trim() }
          : {
              kind: "EXPERIMENT",
              id: candidateExpId.trim(),
              variant_key: candidateVariantKey.trim(),
            };

      if (!Number.isInteger(minimumCandidates) || minimumCandidates < 1 || predictionCoverage <= 0 || predictionCoverage > 1 || referenceCoverage <= 0 || referenceCoverage > 1) throw new Error(t('speakingGates.invalidPolicy'));
      const created = await api.createGate({
        name: name.trim(),
        suite_id: suiteId,
        baseline,
        candidate,
        policy: {
          protocol: "speaking-regression-gate-v1",
          comparison,
          minimum_independent_candidates: minimumCandidates,
          minimum_prediction_coverage: predictionCoverage,
          minimum_reference_coverage: referenceCoverage,
          thresholds,
          max_unknown_billing_attempts: 0,
        },
      });

      setShowCreate(false);
      setName("");
      await load();
      await handleSelectGate(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluateGate = async () => {
    if (!selectedGate) return;
    setEvaluating(true);
    setError("");
    try {
      const rep = await api.evaluateGate(selectedGate.id, holdoutConsent);
      setSelectedReport(rep);
      const updatedReports = await api.gateReports(selectedGate.id);
      setReports(updatedReports);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEvaluating(false);
    }
  };

  const addThreshold = () => {
    if (thresholds.some((t) => t.metric === thresholdMetric)) return;
    setThresholds([...thresholds, { metric: thresholdMetric, max_regression: thresholdMax }]);
  };

  const removeThreshold = (metric: string) => {
    setThresholds(thresholds.filter((t) => t.metric !== metric));
  };

  return (
    <div className={styles.stack}>
      <PageHeading
        eyebrow={t("admin.administration")}
        title={t("speakingGates.title")}
        description={t("speakingGates.description")}
      />
      <LabNavigation current="quality" tool="gates" />

      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}

      {/* Gates List & Create Action */}
      <section className={styles.panel}>
        <div className={styles.cardHeader}>
          <h2>{t("speakingGates.title")} ({gates.length})</h2>
          <button
            className="btn btn-secondary"
            aria-expanded={showCreate}
            onClick={() => setShowCreate((v) => !v)}
          >
            {t("speakingGates.new")}
          </button>
        </div>

        {showCreate && (
          <div className={styles.card} style={{ marginBottom: "16px" }}>
            <h3 className={styles.cardTitle}>{t("speakingGates.new")}</h3>
            <div className={styles.form}>
              <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                <label style={{ flex: "1 1 240px" }}>
                  {t("speakingGates.name")}
                  <input
                    type="text"
                    className="field"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>

                <label style={{ flex: "1 1 240px" }}>
                  {t("speakingGates.suite")}
                  <select
                    className="field"
                    value={suiteId}
                    onChange={(e) => setSuiteId(e.target.value)}
                  >
                    {suites.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} (Rev {s.revision})
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className={styles.grid}>
                <GateSourceSelector title={t("speakingUx.baseline")} kind={baselineKind} onKind={setBaselineKind} fingerprint={baselineFp} onFingerprint={setBaselineFp} experimentId={baselineExpId} onExperimentId={setBaselineExpId} variantKey={baselineVariantKey} onVariantKey={setBaselineVariantKey} />
                <GateSourceSelector title={t("speakingUx.candidate")} kind={candidateKind} onKind={setCandidateKind} fingerprint={candidateFp} onFingerprint={setCandidateFp} experimentId={candidateExpId} onExperimentId={setCandidateExpId} variantKey={candidateVariantKey} onVariantKey={setCandidateVariantKey} />
              </div>
              <details>
                <summary>{t("speakingUx.advancedPolicy")}</summary>
              {/* Thresholds Builder */}
              <div>
                <h4 style={{ margin: "0 0 8px" }}>{t("speakingGates.thresholds")}</h4>
                <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
                  <label style={{ flex: "1 1 180px" }}>
                    {t("speakingGates.metric")}
                    <select
                      className="field"
                      value={thresholdMetric}
                      onChange={(e) =>
                        setThresholdMetric(e.target.value as typeof api.metrics[number])
                      }
                    >
                      {api.metrics.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label style={{ flex: "0 0 140px" }}>
                    {t("speakingGates.maxRegression")}
                    <input
                      type="number"
                      step={0.01}
                      min={0}
                      className="field"
                      value={thresholdMax}
                      onChange={(e) => setThresholdMax(Number(e.target.value))}
                    />
                  </label>

                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={addThreshold}
                  >
                    {t("speakingGates.addThreshold")}
                  </button>
                </div>

                <ul style={{ marginTop: "12px", paddingLeft: "20px" }}>
                  {thresholds.map((th) => (
                    <li key={th.metric} style={{ marginBottom: "4px" }}>
                      <code>{th.metric}</code> — {t("speakingGates.maxRegression")}:
                      <strong>{th.max_regression}</strong>{" "}
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ padding: "2px 6px", fontSize: "12px", minHeight: "24px" }}
                        onClick={() => removeThreshold(th.metric)}
                      >
                        {t("speakingGates.removeThreshold")}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              <label>{t('speakingGates.minimumCandidates')}<input className="field" type="number" min={1} step={1} value={minimumCandidates} onChange={e => setMinimumCandidates(Number(e.target.value))} /></label>
              <label>{t('speakingGates.predictionCoverage')}<input className="field" type="number" min={0.01} max={1} step={0.01} value={predictionCoverage} onChange={e => setPredictionCoverage(Number(e.target.value))} /></label>
              <label>{t('speakingGates.referenceCoverage')}<input className="field" type="number" min={0.01} max={1} step={0.01} value={referenceCoverage} onChange={e => setReferenceCoverage(Number(e.target.value))} /></label>
              <label>{t('speakingGates.comparison')}<select className="field" value={comparison} onChange={e => setComparison(e.target.value as typeof comparison)}><option value="CONFIGURATION">{t("speakingUx.gradingSource")}</option><option value="LEXICAL_ASR">{t("speakingUx.asrComparison")}</option></select></label>
              </details>
              <div className={styles.actions}>
                <button
                  className="btn btn-primary"
                  disabled={loading || !name.trim() || !suiteId || thresholds.length === 0}
                  onClick={() => void handleCreateGate()}
                >
                  {t("speakingUx.createGate")}
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

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">{t("speakingGates.name")}</th>
                <th scope="col">{t("speakingUx.baseline")}</th>
                <th scope="col">{t("speakingUx.candidate")}</th>
                <th scope="col">{t("speakingUx.createdAt")}</th>
                <th scope="col">{t("speakingUx.action")}</th>
              </tr>
            </thead>
            <tbody>
              {gates.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.muted}>
                    {t("speakingGates.empty")}
                  </td>
                </tr>
              ) : (
                gates.map((g) => (
                  <tr key={g.id}>
                    <td>
                      <strong>{g.name}</strong>
                    </td>
                    <td>{t(g.baseline.kind === "GRADING" ? "speakingUx.gradingSource" : "speakingUx.experimentSource")}</td>
                    <td>{t(g.candidate.kind === "GRADING" ? "speakingUx.gradingSource" : "speakingUx.experimentSource")}</td>
                    <td>{new Date(g.created_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ minHeight: "32px", padding: "4px 10px" }}
                        onClick={() => void handleSelectGate(g)}
                      >
                        {t("speakingUx.selectGate")}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Selected Gate Details & Evaluation */}
      {selectedGate && (
        <section className={styles.panel}>
          <div className={styles.cardHeader}>
            <h2>{selectedGate.name}</h2>
            <div className={styles.actions} style={{ margin: 0 }}>
              <button
                className="btn btn-primary"
                disabled={evaluating}
                onClick={() => void handleEvaluateGate()}
              >
                {evaluating
                  ? t("speakingGates.evaluating")
                  : t("speakingGates.evaluate")}
              </button>
            </div>
          </div>

          <div className={styles.muted} style={{ margin: "8px 0" }}>
            <strong>{t("speakingUx.gateId")}</strong> <code>{selectedGate.id}</code> ·{" "}
            <strong>{t("speakingUx.suiteId")}</strong> <code>{selectedGate.suite_id}</code>
          </div>

          <p className={styles.muted}>{t("speakingSuites.holdoutWarning")}</p>
          <label className={styles.check}><input type="checkbox" checked={holdoutConsent} onChange={e => setHoldoutConsent(e.target.checked)} />{t("speakingSuites.holdoutConsent")}</label>
          <div className={styles.grid}>
            {[{ label: t("speakingUx.baseline"), value: selectedGate.baseline }, { label: t("speakingUx.candidate"), value: selectedGate.candidate }].map(source => <div key={source.label}>
              <h3>{source.label}</h3><p>{t(source.value.kind === "GRADING" ? "speakingUx.gradingSource" : "speakingUx.experimentSource")}</p>
              <code>{source.value.kind === "EXPERIMENT" ? source.value.variant_key : source.value.configuration_fingerprint.slice(0, 12) + "…"}</code>
            </div>)}
          </div>
          <details><summary>{t("speakingUx.sources")}</summary><pre>{JSON.stringify({ baseline: selectedGate.baseline, candidate: selectedGate.candidate, policy: selectedGate.policy }, null, 2)}</pre></details>
          {!reports.length && <p className={styles.muted}>{t("speakingGates.noReports")}</p>}
          {/* Reports History */}
          <h3 style={{ marginTop: "24px" }}>
            {t("speakingGates.reports")} ({reports.length})
          </h3>

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", margin: "12px 0" }}>
            {reports.map((rep, idx) => {
              const isSelected = selectedReport?.id === rep.id;
              const badgeClass =
                rep.status === "PASS"
                  ? styles.badgePass
                  : rep.status === "FAIL"
                  ? styles.badgeFail
                  : rep.status === "INCONCLUSIVE"
                  ? styles.badgeInconclusive
                  : styles.badgeInvalid;
              return (
                <button
                  key={rep.id}
                  className="btn btn-secondary"
                  aria-pressed={isSelected}
                  style={{ minHeight: "36px", padding: "4px 12px" }}
                  onClick={() => setSelectedReport(rep)}
                >
                  <span className={`${styles.badge} ${badgeClass}`} style={{ marginRight: "6px" }}>
                    {rep.status}
                  </span>
                  #{idx + 1} ({new Date(rep.created_at).toLocaleTimeString()})
                </button>
              );
            })}
          </div>

          {selectedReport && <GateReport selectedReport={selectedReport} />}
        </section>
      )}
    </div>
  );
}
