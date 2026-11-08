"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./lab.module.css";

export function RecordingWorkspace({ review, labels, evaluation, references }: { review: ReactNode; labels: ReactNode; evaluation: ReactNode; references?: ReactNode }) {
  const { t } = useTranslation();
  const id = useId();
  const [selected, setSelected] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const sections = [
    { label: t("speakingLab.reviewTab"), content: review },
    { label: t("speakingLab.groundTruth"), content: labels },
    { label: t("speakingEval.title"), content: evaluation },
    ...(references ? [{ label: t("speakingResearch.references"), content: references }] : []),
  ];
  return <div className={styles.workspace}>
    <div className={styles.tabs} data-sections={sections.length} role="tablist" aria-label={t("speakingLab.workspace")}>
      {sections.map((section, index) => <button key={index} ref={node => { buttons.current[index] = node; }} type="button" role="tab" id={`${id}-tab-${index}`} aria-controls={`${id}-panel-${index}`} aria-selected={selected === index} tabIndex={selected === index ? 0 : -1} onClick={() => setSelected(index)} onKeyDown={event => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % sections.length;
        else if (event.key === "ArrowLeft") next = (index + sections.length - 1) % sections.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = sections.length - 1;
        else return;
        event.preventDefault(); setSelected(next); buttons.current[next]?.focus();
      }}>{section.label}</button>)}
    </div>
    {sections.map((section, index) => <div key={index} id={`${id}-panel-${index}`} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} hidden={selected !== index} tabIndex={0}>{section.content}</div>)}
  </div>;
}
