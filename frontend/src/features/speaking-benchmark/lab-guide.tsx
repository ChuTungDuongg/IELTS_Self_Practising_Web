"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationKey } from "@/lib/i18n/types";
import styles from "./lab-guide.module.css";

const steps = {
  workflow: ["prepare", "human", "evaluate", "report", "research", "quality"],
  reports: ["filter", "coverage", "metrics", "inspect", "export"],
  reviewer: ["listen", "score", "submit"],
} as const;

export function LabGuide({ mode = "workflow" }: { mode?: keyof typeof steps }) {
  const { t } = useTranslation();
  const title = t(mode === "reports" ? "speakingGuide.reportGuideTitle" : mode === "reviewer" ? "speakingGuide.reviewerTitle" : "speakingGuide.title");
  return <details className={styles.guide} data-speaking-guide>
    <summary>{title}<span>{t(mode === "reports" ? "speakingGuide.reportGuideHint" : mode === "reviewer" ? "speakingGuide.reviewerHint" : "speakingGuide.hint")}</span></summary>
    <div className={styles.content}>
      <p>{t(mode === "reports" ? "speakingGuide.reportIntro" : mode === "reviewer" ? "speakingGuide.reviewerIntro" : "speakingGuide.intro")}</p>
      <table className={styles.table}>
        <caption className="sr-only">{title}</caption>
        <thead><tr><th scope="col">{t("speakingGuide.step")}</th><th scope="col">{t("speakingGuide.instructions")}</th></tr></thead>
        <tbody>{steps[mode].map(step => <tr key={step}>
          <th scope="row">{t(`speakingGuide.${step}Title` as TranslationKey)}</th>
          <td>{t(`speakingGuide.${step}` as TranslationKey)}</td>
        </tr>)}</tbody>
      </table>
      {mode === "reports" && <div className={styles.note}><h3>{t("speakingGuide.statistics")}</h3><p>{t("speakingGuide.statisticsHelp")}</p></div>}
      {mode !== "reviewer" && <p className={styles.note}>{t("speakingGuide.safety")}</p>}
    </div>
  </details>;
}
