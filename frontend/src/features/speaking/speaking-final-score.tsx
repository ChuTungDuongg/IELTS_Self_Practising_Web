"use client";
import { useState } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { saveSpeakingFinalScore, type SpeakingCriteriaInput, type SpeakingReviewData } from "@/lib/api/speaking";
import { saveAssignmentSpeakingScore } from "@/lib/api/classroom-results";
import type { AssignmentGradingScope } from "@/lib/api/grading";
import type { SpeakingAIRun } from "@/lib/api/speaking-ai";

const criteria = ["fc", "lr", "gra", "pr"] as const;
const bands = Array.from({ length: 19 }, (_, index) => (index / 2).toFixed(1));
export function SpeakingFinalScore({ data, assignmentScope, copiedRun }: { data: SpeakingReviewData; assignmentScope?: AssignmentGradingScope; copiedRun?: SpeakingAIRun | null }) {
  const { t } = useTranslation();
  const [review, setReview] = useState(data);
  const [values, setValues] = useState(() => Object.fromEntries(criteria.map(key => [key, data.final_score?.[key].toFixed(1) ?? ""])));
  const [feedback, setFeedback] = useState(() => Object.fromEntries(criteria.map(key => [key, data.final_score?.[`${key}_feedback`] ?? ""])));
  const [source, setSource] = useState<SpeakingAIRun | null | undefined>(undefined);
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState<"saved" | "error" | null>(null);
  const canEdit = review.grading?.can_edit_final === true;
  if (copiedRun && copiedRun !== source && copiedRun.attempt_id === review.attempt_id && canEdit && review.grading?.can_copy_ai_to_final && copiedRun.status === "COMPLETED" && criteria.every(key => copiedRun.criteria[key].status === "COMPLETED" && copiedRun.criteria[key].score !== null)) {
    setSource(copiedRun);
    setValues(Object.fromEntries(criteria.map(key => [key, copiedRun.criteria[key].score!.toFixed(1)])));
    setFeedback(Object.fromEntries(criteria.map(key => [key, copiedRun.criteria[key].feedback ?? ""])));
    setMessage(null);
  }
  async function save() {
    if (!canEdit || saving || criteria.some(key => values[key] === "")) return;
    setSaving(true); setMessage(null);
    const input = Object.fromEntries(criteria.flatMap(key => [[key, Number(values[key])], [`${key}_feedback`, feedback[key].trim() || null]])) as SpeakingCriteriaInput;
    try {
      const result = assignmentScope ? await saveAssignmentSpeakingScore(assignmentScope.classroomId, assignmentScope.assignmentId, review.attempt_id, input) : await saveSpeakingFinalScore(review.attempt_id, input);
      setReview(result); setMessage("saved");
    } catch { setMessage("error"); } finally { setSaving(false); }
  }
  return <section className="speaking-card" aria-label={t(review.grading?.context === "CLASSROOM" ? "grading.teacherFinal" : "grading.practiceFinal")}>
    <h2>{t(review.grading?.context === "CLASSROOM" ? "grading.teacherFinal" : "grading.practiceFinal")}</h2>
    {review.grading?.context === "PERSONAL" ? <p>{t("grading.selfAssessed")}</p> : null}
    {review.grading?.waiting_for_teacher ? <p role="status">{t("grading.waiting")}</p> : null}
    <p>{review.final_score ? t("runner.band", { score: review.final_score.overall_band.toFixed(1) }) : "—"}</p>
    <div className="writing-criteria-grid">{criteria.map(key => <div key={key}>
      {canEdit ? <><label>{t(`speakingAI.criterion.${key}`)}<select className="select-field" aria-label={t("grading.criterion", { criterion: key.toUpperCase() })} value={values[key]} onChange={event => { setValues(current => ({ ...current, [key]: event.target.value })); setMessage(null); }}><option value="">{t("runner.notScored")}</option>{bands.map(band => <option key={band}>{band}</option>)}</select></label>
      <label>{t("runner.criterionFeedback", { criterion: key.toUpperCase() })} · {t("runner.optional")}<textarea className="textarea-field" aria-label={t("grading.feedback", { criterion: key.toUpperCase() })} maxLength={4000} rows={3} value={feedback[key]} onChange={event => { setFeedback(current => ({ ...current, [key]: event.target.value })); setMessage(null); }} /></label></> : <><h3>{t(`speakingAI.criterion.${key}`)}</h3><p>{review.final_score?.[key].toFixed(1) ?? "—"}</p>{review.final_score?.[`${key}_feedback`] ? <p>{review.final_score[`${key}_feedback`]}</p> : null}</>}
    </div>)}</div>
    {canEdit ? <button className="btn btn-primary" disabled={saving || criteria.some(key => values[key] === "")} onClick={() => void save()}>{t(saving ? "common.saving" : "grading.save")}</button> : null}
    {message ? <p role={message === "error" ? "alert" : "status"}>{t(message === "error" ? "grading.error" : "grading.saved")}</p> : null}
  </section>;
}
