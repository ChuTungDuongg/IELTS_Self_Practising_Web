"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeading } from "@/components/ui/page-heading";
import * as api from "@/lib/api/speaking-benchmark-human";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality/quality.module.css";

interface BlindReviewerProps {
  assignmentId: string;
}

export function BlindReviewer({ assignmentId }: BlindReviewerProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<api.BlindAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  // Scoring form
  const [bands, setBands] = useState<Record<string, number | null>>({
    fc: null,
    lr: null,
    gra: null,
    pr: null,
    overall: null,
  });
  const [comments, setComments] = useState({
    fc: "",
    lr: "",
    gra: "",
    pr: "",
    overall: "",
  });
  const [attestation, setAttestation] = useState(false);

  useEffect(() => {
    const dirty = !data?.assessments.length && (Object.values(bands).some(v => v !== null) || Object.values(comments).some(v => v.trim()) || attestation);
    const warn = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [bands, comments, attestation, data]);
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const assignment = await api.blindAssignment(assignmentId);
      setData(assignment);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [assignmentId]);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  const handleSubmit = async () => {
    if (!data || !attestation) return;
    setSubmitting(true);
    setError("");
    try {
      await api.submitBlindAssessment(assignmentId, {
        expected_revision: Math.max(0, ...data.assessments.map(a => a.revision)),
        bands: {
          fc: bands.fc,
          lr: bands.lr,
          gra: bands.gra,
          pr: bands.pr,
          overall: bands.overall,
        },
        comments,
        independently_performed: attestation,
        provenance: "external_unverified",
        source_reference: `blind-reviewer-${assignmentId}`,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.stack}>
        <p role="status">{t("common.loading")}</p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className={styles.stack}>
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      </div>
    );
  }

  if (!data) return null;

  const audioUrl = api.blindAudioUrl(assignmentId);
  const existingAssessment = data.assessments.reduce<api.HumanAssessment | undefined>((latest, a) => !latest || a.revision > latest.revision ? a : latest, undefined);

  return (
    <div className={styles.stack}>
      <PageHeading
        eyebrow={t("speakingReviewer.title")}
        title={`Assignment ${assignmentId.substring(0, 8)}`}
        description={t("speakingReviewer.instructions")}
      />

      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}

      {/* Audio Player */}
      <section className={styles.panel}>
        <h2>Candidate Audio</h2>
        <p className={styles.muted}>
          Duration: {Math.round(data.duration_ms / 1000)} seconds
        </p>
        <audio
          controls
          src={audioUrl}
          style={{ width: "100%", marginTop: "12px" }}
        />
      </section>

      {/* Exam Prompts / Context */}
      <section className={styles.panel}>
        <h2>{t("speakingReviewer.questions")}</h2>
        {data.questions.length === 0 ? (
          <p className={styles.muted}>No verified questions attached.</p>
        ) : (
          <div className={styles.stack} style={{ marginTop: "12px" }}>
            {data.questions.map((q) => (
              <div key={q.id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <strong>Part {q.part_number}</strong> ·{" "}
                  <span className={styles.muted}>{q.prompt_type}</span>
                </div>
                <p style={{ marginTop: "6px" }}>{q.prompt_text}</p>
                {q.cue_points.length > 0 && (
                  <ul style={{ margin: "6px 0 0 20px" }}>
                    {q.cue_points.map((pt, i) => (
                      <li key={i}>{pt}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Assessment Form or Submitted Read-Only Card */}
      <section className={styles.panel}>
        <h2>
          {existingAssessment
            ? t("speakingReviewer.submitted")
            : t("speakingReviewer.title")}
        </h2>

        {existingAssessment ? (
          <div className={styles.card}>
            <div className={styles.noticeWarning} style={{ marginBottom: "16px" }}>
              {t("speakingReviewer.readOnlyNotice")}
            </div>
            <div className={styles.scoreGrid}>
              <div>
                <strong>FC:</strong> {existingAssessment.bands.fc ?? "-"}
              </div>
              <div>
                <strong>LR:</strong> {existingAssessment.bands.lr ?? "-"}
              </div>
              <div>
                <strong>GRA:</strong> {existingAssessment.bands.gra ?? "-"}
              </div>
              <div>
                <strong>PR:</strong> {existingAssessment.bands.pr ?? "-"}
              </div>
              <div>
                <strong>Overall:</strong> {existingAssessment.bands.overall ?? "-"}
              </div>
            </div>
            <div className={styles.stack} style={{ marginTop: "16px" }}>
              {Object.entries(existingAssessment.comments).map(([k, v]) => (
                <div key={k}>
                  <strong>{k.toUpperCase()} Comment:</strong>
                  <p className={styles.muted}>{v || "(none)"}</p>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className={styles.form}>
            <div className={styles.scoreGrid}>
              {(["fc", "lr", "gra", "pr", "overall"] as const).map((crit) => (
                <div key={crit} className={styles.scoreField}>
                  <label htmlFor={`blind-band-${crit}`}>{t(`speakingReviewer.${crit}`)}</label>
                  <input
                    id={`blind-band-${crit}`}
                    type="number"
                    step={0.5}
                    min={0}
                    max={9}
                    className="field"
                    value={bands[crit] ?? ""}
                    onChange={(e) =>
                      setBands({
                        ...bands,
                        [crit]: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                    disabled={submitting}
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
                  <label>{t(`speakingReviewer.${crit}`)} Comments</label>
                  <textarea
                    className="field"
                    value={comments[crit]}
                    onChange={(e) =>
                      setComments({
                        ...comments,
                        [crit]: e.target.value,
                      })
                    }
                    disabled={submitting}
                    placeholder={`Provide feedback on ${crit.toUpperCase()}...`}
                  />
                </div>
              ))}
            </div>

            <div className={styles.check}>
              <input
                type="checkbox"
                id="attestation"
                checked={attestation}
                onChange={(e) => setAttestation(e.target.checked)}
                disabled={submitting}
              />
              <label htmlFor="attestation">
                {t("speakingReviewer.attestationConfirm")}
              </label>
            </div>

            <div className={styles.actions}>
              <button
                className="btn btn-primary"
                disabled={submitting || !attestation}
                onClick={() => void handleSubmit()}
              >
                {submitting
                  ? t("speakingReviewer.submitting")
                  : t("speakingReviewer.submit")}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
