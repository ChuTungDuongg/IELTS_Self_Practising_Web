"use client";

import { useRouter } from "next/navigation";
import type { TranslationKey } from "@/lib/i18n/types";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useRef, useState } from "react";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { StartSpeaking } from "@/features/speaking/start-speaking";
import { rememberAttemptPresentation, type AttemptPresentationMode } from "./attempt-presentation";
import { PresentationDialog } from "./presentation-dialog";
import type { PresentationPreview } from "./presentation-thumbnail";

const choices = [
  ["70 minutes", 4200], ["60 minutes", 3600], ["50 minutes", 3000], ["40 minutes", 2400],
] as const;

export function StartAttempt({ versionId, module, preview }: { versionId: string; module: "READING" | "LISTENING" | "WRITING" | "SPEAKING"; preview?: PresentationPreview }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [duration, setDuration] = useState<string>("3600");
  const [presentation, setPresentation] = useState<AttemptPresentationMode>("PRACTICE");
  const [choosing, setChoosing] = useState(false);
  const [pending, setPending] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const starting = useRef(false);
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  async function start() {
    if (starting.current) return;
    starting.current = true;
    setPending(true);
    setError(null);
    try {
      const countUp = duration === "unlimited";
      const result = await startAttempt({ test_version_id: versionId, module, timer: countUp ? { mode: "COUNT_UP" } : { mode: "COUNTDOWN", duration_seconds: Number(duration) } });
      if (module === "READING" || module === "LISTENING") rememberAttemptPresentation(result, presentation);
      router.push(`/attempt/${result.attempt_id}`);
      setChoosing(false);
    } catch (caught) { setError(caught instanceof ApiError ? caught.message : { message: "practice.attemptFailed" }); starting.current = false; setPending(false); }
  }
  if (module === "SPEAKING") return <StartSpeaking versionId={versionId} />;
  return <div className="mt-5 border-t border-[var(--line)] pt-4">
    <label className="field-label">{t("practice.timer")}<select disabled={pending} value={duration} onChange={(event) => setDuration(event.target.value)} className="select-field mt-2">{choices.map(([, seconds]) => <option key={seconds} value={seconds}>{t("common.minutes", { count: seconds / 60 })}</option>)}<option value="unlimited">{t("practice.unlimited")}</option></select></label><button ref={trigger} type="button" disabled={pending} onClick={() => { if (module === "READING" || module === "LISTENING") setChoosing(true); else void start(); }} className={`btn mt-3 w-full ${module === "LISTENING" ? "btn-listening" : module === "WRITING" ? "btn-writing" : "btn-primary"}`}>{pending ? t("practice.starting") : t("practice.startSkill", { skill: t(moduleTranslationKeys[module]) })}</button>
    {error && !choosing ? <p role="alert" className="notice notice-error mt-3">{typeof error === "string" ? error : t(error.message)}</p> : null}
    {module === "READING" || module === "LISTENING" ? <PresentationDialog open={choosing} module={module} value={presentation} onChange={setPresentation} onClose={() => setChoosing(false)} onConfirm={() => void start()} pending={pending} error={typeof error === "string" ? error : error ? t(error.message) : null} returnFocusRef={trigger} preview={preview} /> : null}
  </div>;
}
