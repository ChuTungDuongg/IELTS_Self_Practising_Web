import { aiTraitNames, type AICriterion, type AITrait } from "@/lib/api/writing-ai";
import { traitSubtitles } from "./writing-ai-progress";
import styles from "./writing-ai-assessment.module.css";

export function CriterionAssessmentCard({ trait, assessment }: { trait: AITrait; assessment: AICriterion }) {
  return <article className={styles.card} aria-label={`AI ${aiTraitNames[trait]}`}>
    <header className={styles.cardHeading}>
      <div><h3>{aiTraitNames[trait]}</h3><small>{traitSubtitles[trait]}</small></div>
      <strong className={styles.band}>Band {assessment.score.toFixed(1)}</strong>
    </header>
    <section><h4>Nhận xét</h4><p>{assessment.feedback}</p></section>
    <section><h4>Điểm làm tốt</h4><ul className={styles.feedbackList}>{assessment.strengths.map((text, index) => <li key={index}><span aria-hidden="true">✓</span>{text}</li>)}</ul></section>
    <section><h4>Cần cải thiện</h4><ul className={styles.feedbackList}>{assessment.improvements.map((text, index) => <li key={index}><span aria-hidden="true">→</span>{text}</li>)}</ul></section>
    <details className={styles.evidence}>
      <summary>Dẫn chứng từ bài viết ({assessment.evidence.length})</summary>
      {assessment.evidence.map((item, index) => <blockquote key={index}><q>{item.quote}</q><p>{item.assessment}</p></blockquote>)}
    </details>
  </article>;
}
