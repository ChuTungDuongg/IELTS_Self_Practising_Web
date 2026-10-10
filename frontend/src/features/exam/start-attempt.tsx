"use client";

import { useRouter } from "next/navigation";
import type { TranslationKey } from "@/lib/i18n/types";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useState } from "react";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";

const choices = [
  ["70 minutes", 4200], ["60 minutes", 3600], ["50 minutes", 3000], ["40 minutes", 2400],
] as const;

export function StartAttempt({ versionId, module }: { versionId: string; module: "READING" | "LISTENING" | "WRITING" }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [duration, setDuration] = useState<string>("3600");
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  async function start() {
    try {
      const countUp = duration === "unlimited";
      const result = await startAttempt({ test_version_id: versionId, module, timer: countUp ? { mode: "COUNT_UP" } : { mode: "COUNTDOWN", duration_seconds: Number(duration) } });
      router.push(`/attempt/${result.attempt_id}`);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : { message: "practice.attemptFailed" }); }
  }
  return <div className="mt-5 border-t border-[var(--line)] pt-4"><label className="field-label">{t("practice.timer")}<select value={duration} onChange={(event) => setDuration(event.target.value)} className="select-field mt-2">{choices.map(([, seconds]) => <option key={seconds} value={seconds}>{t("common.minutes", { count: seconds / 60 })}</option>)}<option value="unlimited">{t("practice.unlimited")}</option></select></label><button onClick={start} className={`btn mt-3 w-full ${module === "LISTENING" ? "btn-listening" : module === "WRITING" ? "btn-writing" : "btn-primary"}`}>{t("practice.startSkill", { skill: t(moduleTranslationKeys[module]) })}</button>{error ? <p role="alert" className="notice notice-error mt-3">{typeof error === "string" ? error : error ? t(error.message) : null}</p> : null}</div>;
}
