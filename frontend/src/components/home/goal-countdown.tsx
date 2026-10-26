"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";
import { useWallClockSeconds } from "@/lib/use-wall-clock";
import styles from "./goal-countdown.module.css";

export function GoalCountdown({ date }: { date: string }) {
  const { t } = useTranslation();
  const now = useWallClockSeconds();
  const validated = new Date(`${date}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(validated.getTime()) || validated.toISOString().slice(0, 10) !== date) return null;
  const target = Date.parse(`${date}T00:00:00+07:00`) / 1000;
  const remaining = now === null ? null : Math.max(0, target - now);
  const days = remaining === null ? "—" : String(Math.floor(remaining / 86400));
  const segment = (divisor: number, modulus: number) => remaining === null ? "--" : String(Math.floor(remaining / divisor) % modulus).padStart(2, "0");
  return <div className={styles.countdown}>
    <div role="timer" aria-live="off" aria-label={t("goals.timeRemaining")} className={styles.units}>
      <span><strong>{days}</strong><small>{t(remaining !== null && Math.floor(remaining / 86400) === 1 ? "goals.day" : "goals.days")}</small></span>
      <span><strong>{segment(3600, 24)}</strong><small>{t("goals.hours")}</small></span>
      <span><strong>{segment(60, 60)}</strong><small>{t("goals.minutes")}</small></span>
      <span><strong>{segment(1, 60)}</strong><small>{t("goals.seconds")}</small></span>
    </div>
    <p>{t(remaining === 0 ? "goals.arrived" : "goals.midnight")}</p>
  </div>;
}
