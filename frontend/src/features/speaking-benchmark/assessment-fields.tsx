"use client";

import { useId } from "react";
import { criteria, type HumanBands } from "@/lib/api/speaking-benchmark-human";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./quality/quality.module.css";

type Comments = Record<typeof criteria[number], string>;

/** Shared, labelled scoring controls; the owning workflow retains all draft state. */
export function AssessmentFields({ bands, onBands, comments, onComments, disabled = false, adjudicated = false }: {
  bands: HumanBands;
  onBands: (value: HumanBands) => void;
  comments?: Comments;
  onComments?: (value: Comments) => void;
  disabled?: boolean;
  adjudicated?: boolean;
}) {
  const { t } = useTranslation();
  const id = useId();
  return <>
    <div className={styles.scoreGrid}>
      {criteria.map(criterion => <div key={criterion} className={styles.scoreField}>
        <label htmlFor={`${id}-band-${criterion}`}>{adjudicated ? t("speakingUx.adjudicatedBand", { criterion: t(`speakingReviewer.${criterion}`) }) : t(`speakingReviewer.${criterion}`)}</label>
        <input id={`${id}-band-${criterion}`} className="field" type="number" step={0.5} min={0} max={9} value={bands[criterion] ?? ""} disabled={disabled} onChange={event => onBands({ ...bands, [criterion]: event.target.value ? Number(event.target.value) : null })} />
      </div>)}
    </div>
    {comments && onComments && <div className={styles.commentsGrid}>
      {criteria.map(criterion => <div key={criterion} className={`${styles.commentField} ${criterion === "overall" ? styles.wide : ""}`}>
        <label htmlFor={`${id}-comment-${criterion}`}>{t("speakingUx.criterionComment", { criterion: t(`speakingReviewer.${criterion}`) })}</label>
        <textarea id={`${id}-comment-${criterion}`} className="field" value={comments[criterion]} disabled={disabled} onChange={event => onComments({ ...comments, [criterion]: event.target.value })} />
      </div>)}
    </div>}
  </>;
}
