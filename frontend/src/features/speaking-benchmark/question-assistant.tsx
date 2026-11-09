"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api/speaking-benchmark-questions";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality/quality.module.css";

interface QuestionAssistantProps {
  sampleId: string;
  blocked?: boolean;
  onDirty?: (dirty: boolean) => void;
  reviewRevision: number;
  onPlay?: (start: number, end: number) => void;
  onDraftUpdated?: () => void;
}

export function QuestionAssistant({
  sampleId,
  blocked = false,
  onDirty,
  reviewRevision,
  onPlay,
  onDraftUpdated,
}: QuestionAssistantProps) {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<api.QuestionJob[]>([]);
  const [activeJob, setActiveJob] = useState<api.QuestionJob | null>(null);
  const [provider, setProvider] = useState<api.QuestionProvider>("azure_stt");
  const [examinerSpeakerId, setExaminerSpeakerId] = useState("SPEAKER_00");
  const [examinerConfirmed, setExaminerConfirmed] = useState(false);
  const [maxSeconds, setMaxSeconds] = useState(300);
  const [maxRequests, setMaxRequests] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<api.QuestionPreflight | null>(null);
  const [audioConsent, setAudioConsent] = useState(false);
  const [estimate, setEstimate] = useState(0);
  const [budget, setBudget] = useState(0);
  const [reconciliationReason, setReconciliationReason] = useState("");
  const [gpuConsent, setGpuConsent] = useState(false);
  const [editedTexts, setEditedTexts] = useState<Record<string, string>>({});
  const [editedParts, setEditedParts] = useState<Record<string, 1 | 2 | 3>>({});

  useEffect(() => { onDirty?.(Object.keys(editedTexts).length > 0 || Object.keys(editedParts).length > 0); }, [editedTexts, editedParts, onDirty]);
  const loadJobs = useCallback(async () => {
    try {
      const list = await api.questionJobs(sampleId);
      setJobs(list);
      setActiveJob(current => list.find(j => j.id === current?.id) ?? list[0] ?? null);
    } catch {
      // Ignored if initial load
    }
  }, [sampleId]);

  useEffect(() => {
    void Promise.resolve().then(loadJobs);
  }, [loadJobs]);

  const handleCreateJob = async () => {
    if (!examinerConfirmed) return;
    setLoading(true);
    setError("");
    try {
      const submissionKey = `job-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      const job = await api.createQuestionJob(sampleId, {
        submission_key: submissionKey,
        review_revision: reviewRevision,
        examiner_speaker_id: examinerSpeakerId,
        examiner_confirmed: true,
        provider,
        max_provider_audio_seconds: maxSeconds,
        max_physical_requests: maxRequests,
      });
      setActiveJob(job);
      setJobs((prev) => [job, ...prev]);
      const pf = await api.prepareQuestions(sampleId, job.id);
      setPreflight(pf);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleStart = async () => {
    if (!activeJob || !preflight || !audioConsent) return;
    setLoading(true);
    setError("");
    try {
      const consent: api.QuestionConsent = {
        provider_audio: true,
        modal_gpu: gpuConsent,
        estimates_usd: Object.fromEntries(Object.keys(preflight.requests).map(key => [key, estimate])),
        max_estimated_cost_usd: budget,
      };
      const unresolved = activeJob.requests.find(r => r.status === "INTERRUPTED_BILLING_UNKNOWN" && !r.reconciliation);
      const updated = activeJob.status === "INTERRUPTED" && unresolved
        ? await api.reconcileQuestions(sampleId, activeJob.id, unresolved.id, reconciliationReason, preflight.preflight_fingerprint, consent)
        : await api.startQuestions(sampleId, activeJob.id, preflight.preflight_fingerprint, consent);
      setActiveJob(updated);
      setPreflight(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleDecision = async (
    proposalId: string,
    action: "ACCEPT" | "REJECT",
    proposal?: api.QuestionProposal
  ) => {
    if (!activeJob) return;
    setLoading(true);
    setError("");
    try {
      const decision: api.QuestionDecision = {
        proposal_id: proposalId,
        action,
        text: editedTexts[proposalId] ?? proposal?.recognized_text,
        part_number: editedParts[proposalId] ?? proposal?.part_number ?? 1,
        candidate_segment_id: proposal?.candidate_segment_id ?? undefined,
        ambiguity_reviewed: true,
      };
      const updated = await api.decideQuestions(
        sampleId,
        activeJob.id,
        reviewRevision,
        activeJob.decisions.length,
        [decision],
        false
      );
      setActiveJob(updated);
      setEditedTexts(current => Object.fromEntries(Object.entries(current).filter(([id]) => id !== proposalId)));
      setEditedParts(current => Object.fromEntries(Object.entries(current).filter(([id]) => id !== proposalId)));

      onDraftUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleBatchAccept = async () => {
    if (!activeJob) return;
    const nonAmbiguous = activeJob.proposals.filter(
      (p) => p.ambiguity_flags.length === 0 && !activeJob.decisions.some(d => d.proposal_id === p.id)
    );
    if (nonAmbiguous.length === 0) return;
    setLoading(true);
    setError("");
    try {
      const decisions: api.QuestionDecision[] = nonAmbiguous.map((p) => ({
        proposal_id: p.id,
        action: "ACCEPT",
        text: editedTexts[p.id] ?? p.recognized_text,
        part_number: editedParts[p.id] ?? p.part_number,
        candidate_segment_id: p.candidate_segment_id ?? undefined,
        ambiguity_reviewed: true,
      }));
      const updated = await api.decideQuestions(
        sampleId,
        activeJob.id,
        reviewRevision,
        activeJob.decisions.length,
        decisions,
        true
      );
      setActiveJob(updated);
      const acceptedIds = new Set(nonAmbiguous.map(proposal => proposal.id));
      setEditedTexts(current => Object.fromEntries(Object.entries(current).filter(([id]) => !acceptedIds.has(id))));
      setEditedParts(current => Object.fromEntries(Object.entries(current).filter(([id]) => !acceptedIds.has(id))));

      onDraftUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  if (blocked) return <p role="status" className="notice">{t("speakingQuestions.saveFirst")}</p>;
  return (
    <div className={styles.stack}>
      <section className={styles.panel}>
        <h2>
          {t("speakingQuestions.title")} {jobs.length > 0 ? `(${jobs.length})` : ""}
        </h2>
        <p className={styles.muted}>{t("speakingQuestions.description")}</p>

        {error && (
          <p role="alert" className="notice notice-error">
            {error}
          </p>
        )}

        <p className={styles.muted}>{t("speakingUx.questionFlow")}</p>
        <details open={!activeJob || activeJob.proposals.length === 0}>
          <summary>{t("speakingUx.setup")}</summary>
        <div className={styles.toolbar}>
          <label>
            {t("speakingQuestions.provider")}
            <select
              className="field"
              value={provider}
              onChange={(e) => setProvider(e.target.value as api.QuestionProvider)}
              disabled={loading}
            >
              {api.questionProviders.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t("speakingUx.examinerId")}
            <input
              type="text"
              className="field"
              value={examinerSpeakerId}
              onChange={(e) => setExaminerSpeakerId(e.target.value)}
              disabled={loading}
            />
          </label>

          <label>
            {t("speakingQuestions.maxSeconds")}
            <input
              type="number"
              className="field"
              value={maxSeconds}
              onChange={(e) => setMaxSeconds(Number(e.target.value))}
              disabled={loading}
            />
          </label>

          <label>
            {t("speakingQuestions.maxRequests")}
            <input
              type="number"
              className="field"
              value={maxRequests}
              onChange={(e) => setMaxRequests(Number(e.target.value))}
              disabled={loading}
            />
          </label>
        </div>

        <div className={styles.check}>
          <input
            type="checkbox"
            id="examinerConfirmed"
            checked={examinerConfirmed}
            onChange={(e) => setExaminerConfirmed(e.target.checked)}
            disabled={loading}
          />
          <label htmlFor="examinerConfirmed">
            {t("speakingQuestions.confirmExaminer")}
          </label>
        </div>

        <div className={styles.actions}>
          <button
            className="btn btn-primary"
            disabled={loading || !examinerConfirmed}
            onClick={() => void handleCreateJob()}
          >
            {t("speakingQuestions.extract")}
          </button>
        </div>

        </details>

        {preflight && (
          <div className={styles.card} style={{ marginTop: "16px" }}>
            <div className={styles.cardHeader}>
              <h3 className={styles.cardTitle}>{t("speakingQuestions.preflight")}</h3>
            </div>
            <p className={styles.muted}>
              {t("speakingQuestions.estimatedSeconds")}:{" "}
              {preflight.provider_audio_seconds} s
            </p>

            {preflight.blockers.length > 0 && (
              <div className={styles.noticeWarning}>
                <strong>{t("speakingQuestions.blockers")}:</strong>
                <ul>
                  {preflight.blockers.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              </div>
            )}

            {preflight.warnings.length > 0 && (
              <div className={styles.muted}>
                <strong>{t("speakingQuestions.warnings")}:</strong>
                <ul>
                  {preflight.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            <label>{t("speakingQuestions.estimate")}<input className="field" type="number" min={0} step={0.01} value={estimate} onChange={e => setEstimate(Number(e.target.value))} /></label>
            <label>{t("speakingQuestions.budget")}<input className="field" type="number" min={0} step={0.01} value={budget} onChange={e => setBudget(Number(e.target.value))} /></label>
            {activeJob?.status === "INTERRUPTED" && <label>{t("speakingQuestions.reconciliation")}<textarea className="field" value={reconciliationReason} onChange={e => setReconciliationReason(e.target.value)} /></label>}
            <div className={styles.check}>
              <input
                type="checkbox"
                id="qAudioConsent"
                checked={audioConsent}
                onChange={(e) => setAudioConsent(e.target.checked)}
              />
              <label htmlFor="qAudioConsent">
                {t("speakingQuestions.audioConsent")}
              </label>
            </div>

            {Object.keys(preflight.requests).includes("faster_whisper_modal") && (
              <div className={styles.check}>
                <input
                  type="checkbox"
                  id="qGpuConsent"
                  checked={gpuConsent}
                  onChange={(e) => setGpuConsent(e.target.checked)}
                />
                <label htmlFor="qGpuConsent">
                  {t("speakingQuestions.gpuConsent")}
                </label>
              </div>
            )}

            <div className={styles.actions}>
              <button
                className="btn btn-primary"
                disabled={loading || !audioConsent || !preflight.can_start || budget < estimate || (Object.keys(preflight.requests).some(key => key !== "faster_whisper_local") && estimate <= 0) || (activeJob?.status === "INTERRUPTED" && !reconciliationReason.trim())}
                onClick={() => void handleStart()}
              >
                {t("speakingQuestions.startJob")}
              </button>
            </div>
          </div>
        )}
      </section>

      {jobs.length > 1 && <label className={styles.form}>{t("speakingUx.questionHistory")}
        <select className="field" value={activeJob?.id ?? ""} onChange={event => { setActiveJob(jobs.find(job => job.id === event.target.value) ?? null); setPreflight(null); }}>
          {jobs.map((job, index) => <option key={job.id} value={job.id}>{index + 1} · {job.status} · {job.created_at}</option>)}
        </select>
      </label>}
      {activeJob && (
        <section className={styles.panel}>
          <div className={styles.cardHeader}>
            <h2>{t("speakingQuestions.proposals")} ({activeJob.proposals.length})</h2>
            <span className={styles.badge}>{activeJob.status}</span>
            <button className="btn btn-secondary" disabled={loading} onClick={() => void loadJobs()}>{t("common.retry")}</button>
            {['DRAFT','PENDING','RUNNING','INTERRUPTED'].includes(activeJob.status) && <button className="btn btn-secondary" disabled={loading} onClick={() => void api.cancelQuestions(sampleId, activeJob.id).then(setActiveJob).catch(e => setError(String(e)))}>{t("common.cancel")}</button>}
            {['DRAFT','INTERRUPTED'].includes(activeJob.status) && <button className="btn btn-secondary" disabled={loading} onClick={() => void api.prepareQuestions(sampleId, activeJob.id).then(setPreflight).catch(e => setError(String(e)))}>{t("speakingQuestions.preflight")}</button>}
          </div>

          {activeJob.proposals.length === 0 ? (
            <p className={styles.muted}>{t("speakingQuestions.noProposals")}</p>
          ) : (
            <>
              <div className={styles.actions}>
                <button
                  className="btn btn-secondary"
                  disabled={loading}
                  onClick={() => void handleBatchAccept()}
                >
                  {t("speakingQuestions.batchAccept")}
                </button>
              </div>

              <div className={styles.stack} style={{ marginTop: "16px" }}>
                {activeJob.proposals.map((proposal) => {
                  const hasFlags = proposal.ambiguity_flags.length > 0;
                  const decision = activeJob.decisions.findLast(d => d.proposal_id === proposal.id);
                  const isDecided = Boolean(decision);
                  const confirmedText = typeof decision?.text === "string" ? decision.text : proposal.recognized_text;
                  const confirmedPart = decision?.part_number === 1 || decision?.part_number === 2 || decision?.part_number === 3 ? decision.part_number : proposal.part_number;
                  return (
                    <div key={proposal.id} className={styles.card}>
                      <div className={styles.cardHeader}>
                        <div>
                          <strong>{t("speakingUx.part", { part: editedParts[proposal.id] ?? confirmedPart })}</strong> ·{" "}
                          <span>{proposal.question_type}</span>
                        </div>
                        <div className={styles.proposalMeta}>
                          <span>
                            {Math.round(proposal.start_ms / 1000)}s -{" "}
                            {Math.round(proposal.end_ms / 1000)}s
                          </span>
                          {onPlay && (
                            <button
                              className="btn btn-ghost"
                              style={{ padding: "2px 8px", minHeight: "30px" }}
                              onClick={() => onPlay(proposal.start_ms, proposal.end_ms)}
                            >
                              {t("speakingLab.playWindow")}
                            </button>
                          )}
                        </div>
                      </div>

                      {hasFlags && (
                        <div className={styles.proposalFlags}>
                          {proposal.ambiguity_flags.map((flag) => (
                            <span key={flag} className={styles.flagBadge}>
                              {flag}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className={styles.form} style={{ marginTop: "10px" }}>
                        <label>
                          {t("speakingQuestions.recognizedText")}
                          <input
                            type="text"
                            className="field"
                            value={editedTexts[proposal.id] ?? confirmedText}
                            onChange={(e) =>
                              setEditedTexts({
                                ...editedTexts,
                                [proposal.id]: e.target.value,
                              })
                            }
                            disabled={loading || isDecided}
                          />
                        </label>

                        <div style={{ display: "flex", gap: "12px" }}>
                          <label style={{ flex: "0 0 120px" }}>
                            {t("speakingQuestions.part")}
                            <select
                              className="field"
                              value={editedParts[proposal.id] ?? confirmedPart}
                              onChange={(e) =>
                                setEditedParts({
                                  ...editedParts,
                                  [proposal.id]: Number(e.target.value) as 1 | 2 | 3,
                                })
                              }
                              disabled={loading || isDecided}
                            >
                              <option value={1}>{t("speakingUx.part", { part: 1 })}</option>
                              <option value={2}>{t("speakingUx.part", { part: 2 })}</option>
                              <option value={3}>{t("speakingUx.part", { part: 3 })}</option>
                            </select>
                          </label>
                        </div>
                      </div>

                      <div className={styles.actions}>
                        <button
                          className="btn btn-primary"
                          disabled={loading || isDecided}
                          onClick={() =>
                            void handleDecision(proposal.id, "ACCEPT", proposal)
                          }
                        >
                          {t("speakingQuestions.accept")}
                        </button>
                        <button
                          className="btn btn-ghost"
                          disabled={loading || isDecided}
                          onClick={() =>
                            void handleDecision(proposal.id, "REJECT", proposal)
                          }
                        >
                          {t("speakingQuestions.reject")}
                        </button>
                        {!isDecided && <span className={styles.muted}>{t("speakingUx.pending")}</span>}
                        {isDecided && (
                          <span className={styles.muted} style={{ fontSize: "13px" }}>
                            {t(decision?.action === "ACCEPT" ? "speakingUx.accepted" : "speakingUx.rejected")}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
