"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { startAttempt } from "@/lib/api/attempts";

export function StartSpeaking({ versionId }: { versionId: string }) {
  const { t } = useTranslation(); const router = useRouter(); const pending = useRef(false);
  const [mode, setMode] = useState<"PRACTICE" | "EXAM">("PRACTICE"); const [busy, setBusy] = useState(false); const [error, setError] = useState(false);
  async function start() {
    if (pending.current) return; pending.current = true; setBusy(true); setError(false);
    try { const attempt = await startAttempt({ test_version_id: versionId, module: "SPEAKING", speaking_mode: mode, timer: { mode: "COUNT_UP" } }); router.push(`/attempt/${attempt.attempt_id}`); }
    catch { setError(true); pending.current = false; setBusy(false); }
  }
  return <div className="practice-start"><label className="field-label">{t("speakingRuntime.mode")}<select aria-label={t("speakingRuntime.mode")} value={mode} disabled={busy} onChange={(event) => setMode(event.target.value as "PRACTICE" | "EXAM")}><option value="PRACTICE">{t("speakingRuntime.practice")}</option><option value="EXAM">{t("speakingRuntime.exam")}</option></select></label><p>{t("speakingRuntime.authoredTimers")}</p><button className="btn btn-primary" disabled={busy} onClick={() => void start()}>{t("speakingRuntime.start")}</button>{error ? <p role="alert" className="notice notice-error">{t("speakingRuntime.saveError")}</p> : null}</div>;
}
