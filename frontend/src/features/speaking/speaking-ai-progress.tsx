"use client";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { SpeakingAIRun } from "@/lib/api/speaking-ai";

const stages = ["PENDING", "QUALITY_CHECK", "TRANSCRIBING", "ANALYSING_AUDIO", "BUILDING_EVIDENCE", "SCORING", "GENERATING_FEEDBACK", "COMPLETED"] as const;
export function SpeakingAIProgress({ run }: { run: SpeakingAIRun }) {
  const { t } = useTranslation();
  const active = run.status === "PENDING" || run.status === "RUNNING";
  return <div className="speaking-ai-progress" data-active={active}>
    <p role="status" aria-live="polite">{t(`speakingAI.stage.${run.stage}`)}</p>
    {active ? <progress aria-label={t("speakingAI.progress")} max={stages.length - 1} value={Math.max(0, stages.indexOf(run.stage as typeof stages[number]))} /> : null}
  </div>;
}
