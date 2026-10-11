"use client";

import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { aiTraits, traitNamesForTask, type AIPracticeFeedback, type AIRelevance } from "@/lib/api/writing-ai";
import { presentAIFeedback } from "./ai-feedback-presentation";
import styles from "./writing-ai-assessment.module.css";

export function WritingRelevanceNotice({ relevance }: { relevance?: AIRelevance | null }) {
  const { t } = useTranslation();
  return relevance?.short_circuit_applied ? <aside className={styles.trace} aria-label={t("writingAI.relevanceTitle")}>
    <strong>{t("writingAI.relevanceTitle")}</strong>
    <p>{presentAIFeedback(relevance.reason)}</p>
    <p>{t("writingAI.relevanceExplanation")}</p>
  </aside> : null;
}

export function SavedAIPracticeFeedback({ feedback, taskNumber }: { feedback: AIPracticeFeedback; taskNumber: 1 | 2 }) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const names = traitNamesForTask(taskNumber);
  const formatTime = (time: string) => new Date(time).toLocaleString(locale === "vi" ? "vi-VN" : "en-GB");
  return <section className={styles.trace} aria-label={t("writingAI.savedTitle")}>
    <div className={styles.heading}><h3>{t("writingAI.savedTitle")}</h3><span className={styles.badge}>{t("writingAI.advisoryBadge")}</span></div>
    <p>{t("writingAI.savedAt", { time: formatTime(feedback.created_at) })} · {t("writingAI.updatedAt", { time: formatTime(feedback.updated_at) })}</p>
    <WritingRelevanceNotice relevance={feedback.relevance} />
    <div className={styles.criteria}>{aiTraits.map(trait => <article key={trait} className={styles.card}>
      <div className={styles.cardHeading}><h4>{names[trait]}</h4><strong className={styles.band}>{feedback.criteria[trait].score.toFixed(1)}</strong></div>
      <p className={styles.feedback}>{presentAIFeedback(feedback.criteria[trait].feedback)}</p>
    </article>)}</div>
  </section>;
}
