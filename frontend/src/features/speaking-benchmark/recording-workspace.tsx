"use client";

import type { ReactNode } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { PersistentSections } from "./persistent-sections";
import styles from "./lab.module.css";

export function RecordingWorkspace({ review, labels, evaluation, references, questions, human }: {
  review: ReactNode;
  labels: ReactNode;
  evaluation: ReactNode;
  references?: ReactNode;
  questions?: ReactNode;
  human?: ReactNode;
}) {
  const { t } = useTranslation();
  return <div className={styles.workspace}>
    <PersistentSections label={t("speakingLab.workspace")} sections={[
      { id: "preparation", label: t("speakingUx.preparation"), content: questions ? <PersistentSections compact label={t("speakingUx.preparationTasks")} sections={[
        { id: "review", label: t("speakingLab.reviewTab"), content: review },
        { id: "questions", label: t("speakingUx.questionAssistant"), content: questions },
      ]} /> : review },
      { id: "human", label: t("speakingUx.humanAssessment"), content: human ? <PersistentSections compact label={t("speakingUx.humanTasks")} sections={[
        { id: "label", label: t("speakingUx.humanReference"), content: labels },
        { id: "raters", label: t("speakingUx.ratersConsensus"), content: human },
      ]} /> : labels },
      { id: "evaluation", label: t("speakingEval.title"), content: evaluation },
      ...(references ? [{ id: "research", label: t("speakingUx.research"), content: references }] : []),
    ]} />
  </div>;
}
