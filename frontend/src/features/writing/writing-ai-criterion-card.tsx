import { traitNamesForTask, type AICriterion, type AITrait } from "@/lib/api/writing-ai";
import type { Task1Analysis } from "@/lib/api/task1-visual";
import { traitSubtitles } from "./writing-ai-progress";
import { presentAIFeedback } from "./ai-feedback-presentation";
import styles from "./writing-ai-assessment.module.css";
import { Task1VisualDetails } from "./writing-ai-visual-details";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function CriterionAssessmentCard({ trait, assessment, taskNumber = 2, visualAnalysis, generatingFeedback = false, feedbackFailed = false }: { trait: AITrait; assessment: AICriterion; taskNumber?: 1 | 2; visualAnalysis?: Task1Analysis | null; generatingFeedback?: boolean; feedbackFailed?: boolean }) {
  const { t } = useTranslation();
  const pending = !feedbackFailed && (generatingFeedback || assessment.feedback_status === "PENDING");
  const unavailable = feedbackFailed || assessment.feedback_status === "UNAVAILABLE";
  const aiTraitNames = traitNamesForTask(taskNumber);
  return <article className={styles.card} aria-label={`AI ${aiTraitNames[trait]}`}>
    <header className={styles.cardHeading}>
      <div><h3>{aiTraitNames[trait]}</h3><small>{traitSubtitles[trait]}</small></div>
      <strong className={styles.band}>Band {assessment.score.toFixed(1)}</strong>
    </header>
    <section><h4>{t("writingAI.feedbackVerdict")}</h4><p className={styles.feedback}>{pending ? t("writingAI.generatingFeedback") : unavailable ? t("writingAI.feedbackUnavailable") : presentAIFeedback(assessment.feedback)}</p></section>
    {!pending && assessment.strengths.length ? <section><h4>{t("writingAI.whatWorks")}</h4><ul className={styles.feedbackList}>{assessment.strengths.map((text, index) => <li key={index}><span aria-hidden="true">✓</span><p>{presentAIFeedback(text)}</p></li>)}</ul></section> : null}
    {!pending && assessment.improvements.length ? <section><h4>{t("writingAI.fixNext")}</h4><ul className={styles.feedbackList}>{assessment.improvements.map((text, index) => <li key={index}><span aria-hidden="true">→</span><p>{presentAIFeedback(text)}</p></li>)}</ul></section> : null}
    {trait === "ta" && taskNumber === 1 && visualAnalysis ? <Task1VisualDetails analysis={visualAnalysis} /> : null}
    <details className={styles.evidence}>
      <summary>Dẫn chứng từ bài viết ({assessment.evidence.length})</summary>
      {assessment.evidence.map((item, index) => <blockquote key={index}><q>{item.quote}</q><p>{presentAIFeedback(item.assessment)}</p></blockquote>)}
    </details>
  </article>;
}
