"use client";

import Link from "next/link";
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
        action={
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark">
              {t("speakingLab.title")}
            </Link>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark/quality">
              {t("speakingLab.quality")}
            </Link>
            <Link className="btn btn-secondary" href="/admin/speaking-benchmark/suites">
              {t("speakingLab.suites")}
            </Link>
          </div>
        }
      />

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
            className="btn btn-primary"
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
                    placeholder="e.g. Whisper-v3 vs Local Whisper Gate"
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

              {/* Baseline Selection */}
              <div className={styles.card}>
                <h4 style={{ margin: "0 0 8px" }}>{t("speakingGates.baseline")}</h4>
                <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                  <label style={{ flex: "0 0 160px" }}>
                    Selector Kind
                    <select
                      className="field"
                      value={baselineKind}
                      onChange={(e) =>
                        setBaselineKind(e.target.value as "GRADING" | "EXPERIMENT")
                      }
                    >
                      <option value="GRADING">GRADING (Config FP)</option>
                      <option value="EXPERIMENT">EXPERIMENT (Variant)</option>
                    </select>
                  </label>

                  {baselineKind === "GRADING" ? (
                    <label style={{ flex: "1 1 280px" }}>
                      Configuration Fingerprint (64 hex)
                      <input
                        type="text"
                        className="field"
                        value={baselineFp}
                        onChange={(e) => setBaselineFp(e.target.value)}
                        placeholder="64 hex characters"
                      />
                    </label>
                  ) : (
                    <>
                      <label style={{ flex: "1 1 200px" }}>
                        Experiment ID (UUID)
                        <input
                          type="text"
                          className="field"
                          value={baselineExpId}
                          onChange={(e) => setBaselineExpId(e.target.value)}
                        />
                      </label>
                      <label style={{ flex: "1 1 160px" }}>
                        Variant Key
                        <input
                          type="text"
                          className="field"
                          value={baselineVariantKey}
                          onChange={(e) => setBaselineVariantKey(e.target.value)}
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>

              {/* Candidate Selection */}
              <div className={styles.card}>
                <h4 style={{ margin: "0 0 8px" }}>{t("speakingGates.candidate")}</h4>
                <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
                  <label style={{ flex: "0 0 160px" }}>
                    Selector Kind
                    <select
                      className="field"
                      value={candidateKind}
                      onChange={(e) =>
                        setCandidateKind(e.target.value as "GRADING" | "EXPERIMENT")
                      }
                    >
                      <option value="GRADING">GRADING (Config FP)</option>
                      <option value="EXPERIMENT">EXPERIMENT (Variant)</option>
                    </select>
                  </label>

                  {candidateKind === "GRADING" ? (
                    <label style={{ flex: "1 1 280px" }}>
                      Configuration Fingerprint (64 hex)
                      <input
                        type="text"
                        className="field"
                        value={candidateFp}
                        onChange={(e) => setCandidateFp(e.target.value)}
                        placeholder="64 hex characters"
                      />
                    </label>
                  ) : (
                    <>
                      <label style={{ flex: "1 1 200px" }}>
                        Experiment ID (UUID)
                        <input
                          type="text"
                          className="field"
                          value={candidateExpId}
                          onChange={(e) => setCandidateExpId(e.target.value)}
                        />
                      </label>
                      <label style={{ flex: "1 1 160px" }}>
                        Variant Key
                        <input
                          type="text"
                          className="field"
                          value={candidateVariantKey}
                          onChange={(e) => setCandidateVariantKey(e.target.value)}
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>

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
                      <code>{th.metric}</code> — max regression:{" "}
                      <strong>{th.max_regression}</strong>{" "}
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ padding: "2px 6px", fontSize: "12px", minHeight: "24px" }}
                        onClick={() => removeThreshold(th.metric)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              <label>{t('speakingGates.minimumCandidates')}<input className="field" type="number" min={1} step={1} value={minimumCandidates} onChange={e => setMinimumCandidates(Number(e.target.value))} /></label>
              <label>{t('speakingGates.predictionCoverage')}<input className="field" type="number" min={0.01} max={1} step={0.01} value={predictionCoverage} onChange={e => setPredictionCoverage(Number(e.target.value))} /></label>
              <label>{t('speakingGates.referenceCoverage')}<input className="field" type="number" min={0.01} max={1} step={0.01} value={referenceCoverage} onChange={e => setReferenceCoverage(Number(e.target.value))} /></label>
              <label>{t('speakingGates.comparison')}<select className="field" value={comparison} onChange={e => setComparison(e.target.value as typeof comparison)}><option value="CONFIGURATION">CONFIGURATION</option><option value="LEXICAL_ASR">LEXICAL_ASR</option></select></label>
              <div className={styles.actions}>
                <button
                  className="btn btn-primary"
                  disabled={loading || !name.trim() || !suiteId || thresholds.length === 0}
                  onClick={() => void handleCreateGate()}
                >
                  Create Gate
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
                <th>{t("speakingGates.name")}</th>
                <th>Baseline</th>
                <th>Candidate</th>
                <th>Created At</th>
                <th>Action</th>
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
                    <td>{g.baseline.kind}</td>
                    <td>{g.candidate.kind}</td>
                    <td>{new Date(g.created_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="btn btn-secondary"
                        style={{ minHeight: "32px", padding: "4px 10px" }}
                        onClick={() => void handleSelectGate(g)}
                      >
                        Select Gate
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
      <label className={styles.check}><input type="checkbox" checked={holdoutConsent} onChange={e => setHoldoutConsent(e.target.checked)} />{t('speakingSuites.holdoutConsent')}</label>
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
            <strong>Gate ID:</strong> <code>{selectedGate.id}</code> ·{" "}
            <strong>Suite ID:</strong> <code>{selectedGate.suite_id}</code>
          </div>

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
                  className={`btn ${isSelected ? "btn-primary" : "btn-secondary"}`}
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

          {/* Selected Report Inspection */}
          {selectedReport && (
            <div className={styles.card} style={{ marginTop: "16px" }}>
              <div className={styles.cardHeader}>
                <div>
                  <h3 className={styles.cardTitle}>{t("speakingGates.report")}</h3>
                  <div className={styles.muted} style={{ fontSize: "12px" }}>
                    Report ID: <code>{selectedReport.id}</code>
                  </div>
                </div>

                <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                  <span
                    className={`${styles.badge} ${
                      selectedReport.status === "PASS"
                        ? styles.badgePass
                        : selectedReport.status === "FAIL"
                        ? styles.badgeFail
                        : selectedReport.status === "INCONCLUSIVE"
                        ? styles.badgeInconclusive
                        : styles.badgeInvalid
                    }`}
                  >
                    {selectedReport.status}
                  </span>
                  <a
                    className="btn btn-secondary"
                    style={{ minHeight: "32px", padding: "4px 10px" }}
                    href={api.regressionExportUrl(selectedReport.id, "csv")}
                    download
                  >
                    {t("speakingGates.exportCsv")}
                  </a>
                  <a
                    className="btn btn-secondary"
                    style={{ minHeight: "32px", padding: "4px 10px" }}
                    href={api.regressionExportUrl(selectedReport.id, "json")}
                    download
                  >
                    {t("speakingGates.exportJson")}
                  </a>
                </div>
              </div>

              {/* Metrics Table */}
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>{t("speakingGates.metric")}</th>
                      <th className={styles.numeric}>Baseline</th>
                      <th className={styles.numeric}>Candidate</th>
                      <th className={styles.numeric}>{t("speakingGates.difference")}</th>
                      <th className={styles.numeric}>{t("speakingGates.relDifference")}</th>
                      <th className={styles.numeric}>{t("speakingGates.maxRegression")}</th>
                      <th>Status</th>
                      <th>{t("speakingGates.bootstrapCI")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const repData = selectedReport.report as Record<string, unknown>;
                      const metricResults = ((repData.metrics ?? []) as Array<Record<string, unknown>>).map(m => ({
                        ...m, baseline_value:m.baseline, candidate_value:m.candidate, diff:m.difference,
                        rel_diff_pct: typeof m.relative_difference === 'number' ? m.relative_difference * 100 : null,
                        max_regression:m.tolerable_regression, passed:m.status === 'PASS',
                        ci_lower: (m.paired as {ci95?:number[]})?.ci95?.[0] ?? null,
                        ci_upper: (m.paired as {ci95?:number[]})?.ci95?.[1] ?? null,
                      })) as Array<{
                        metric: string;
                        baseline_value: number | null;
                        candidate_value: number | null;
                        diff: number | null;
                        rel_diff_pct: number | null;
                        max_regression: number;
                        passed: boolean;
                        status: string;
                        ci_lower: number | null;
                        ci_upper: number | null;
                      }>;

                      if (metricResults.length === 0) {
                        return (
                          <tr>
                            <td colSpan={8} className={styles.muted}>
                              No metric details recorded in report.
                            </td>
                          </tr>
                        );
                      }

                      return metricResults.map((m) => (
                        <tr key={m.metric}>
                          <td>
                            <code>{m.metric}</code>
                          </td>
                          <td className={styles.numeric}>
                            {m.baseline_value !== null ? m.baseline_value.toFixed(4) : "-"}
                          </td>
                          <td className={styles.numeric}>
                            {m.candidate_value !== null ? m.candidate_value.toFixed(4) : "-"}
                          </td>
                          <td className={styles.numeric}>
                            {m.diff !== null ? (m.diff > 0 ? `+${m.diff.toFixed(4)}` : m.diff.toFixed(4)) : "-"}
                          </td>
                          <td className={styles.numeric}>
                            {m.rel_diff_pct !== null ? `${m.rel_diff_pct.toFixed(2)}%` : "-"}
                          </td>
                          <td className={styles.numeric}>{m.max_regression.toFixed(4)}</td>
                          <td>
                            <span
                              className={`${styles.badge} ${
                                m.passed ? styles.badgePass : styles.badgeFail
                              }`}
                            >
                              {m.status}
                            </span>
                          </td>
                          <td>
                            {m.ci_lower !== null && m.ci_upper !== null
                              ? `[${m.ci_lower.toFixed(3)}, ${m.ci_upper.toFixed(3)}]`
                              : "n/a"}
                          </td>
                        </tr>
                      ));
                    })()}
                  </tbody>
                </table>
              </div>

              {/* Denominators & Unknown Billing Status */}
              <div className={styles.counters} style={{ marginTop: "16px" }}>
                <div className={styles.counterItem}>
                  <div className={styles.counterLabel}>Protocol</div>
                  <div style={{ fontSize: "14px", fontWeight: 600 }}>
                    {selectedReport.protocol}
                  </div>
                </div>
                <div className={styles.counterItem}>
                  <div className={styles.counterLabel}>
                    {t("speakingGates.unknownBilling")}
                  </div>
                  <div className={styles.counterValue}>
                    {String(
                      (selectedReport.report as Record<string, unknown>)
                        ?.candidate_unknown_billing_requests ?? 0
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
