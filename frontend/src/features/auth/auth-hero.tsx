"use client";

import type { ReactNode } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { AuthIcon } from "./auth-icons";
import styles from "./auth.module.css";

const features = [
  { icon: "progress", message: "auth.trackProgress" },
  { icon: "target", message: "auth.focusedPractice" },
  { icon: "clock", message: "auth.practiceTime" },
  { icon: "flag", message: "auth.examReady" },
] as const;

export function AuthHero({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const title = t("gravity.authTitle");
  const emphasis = t("gravity.authTitleEmphasis");
  const hasEmphasis = title.endsWith(emphasis);

  return <aside className={styles.hero} aria-labelledby="auth-intro-title">
    <p className={styles.eyebrow}>BandPilot <span aria-hidden="true">/</span> IELTS</p>
    <h2 id="auth-intro-title" className={styles.title}>
      {hasEmphasis ? <>{title.slice(0, -emphasis.length)}<span className={styles.emphasis}>{emphasis}</span></> : title}
    </h2>
    <p className={styles.description}>{t("gravity.authDescription")}</p>
    <ul className={styles.features}>
      {features.map(feature => <li key={feature.message}><AuthIcon name={feature.icon} /><span>{t(feature.message)}</span></li>)}
    </ul>
    {children}
  </aside>;
}
