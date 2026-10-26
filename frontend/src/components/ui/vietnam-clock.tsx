"use client";

import { useWallClockSeconds } from "@/lib/use-wall-clock";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./vietnam-clock.module.css";

const formatter = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Ho_Chi_Minh", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
export function VietnamClock() {
  const { t } = useTranslation();
  const seconds = useWallClockSeconds();
  const date = seconds === null ? null : new Date(seconds * 1000);
  const time = date ? formatter.format(date) : "--:--:--";
  return <time className={styles.clock} dateTime={date?.toISOString()} aria-label={`${t("shell.localTime")}: ${time} GMT+7`}><span>{time}</span><small>GMT+7</small></time>;
}
