"use client";

import { useRef, useState } from "react";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useRouter } from "next/navigation";
import { startAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { rememberAttemptPresentation, type AttemptPresentationMode } from "@/features/exam/attempt-presentation";
import { PresentationDialog } from "@/features/exam/presentation-dialog";
import type { PresentationPreview } from "@/features/exam/presentation-thumbnail";

type FocusedTarget = { module: "READING"; unitId: string; taskNumber?: never }
  | { module: "LISTENING"; unitId: string; taskNumber?: never }
  | { module: "WRITING"; unitId: string; taskNumber: number }
  | { module: "SPEAKING"; unitId: string; partNumber: 1 | 2 | 3; taskNumber?: never };

export function StartFocusedPractice({ versionId, target, unavailableReason, preview }: { versionId: string; target: FocusedTarget; unavailableReason?: string; preview?: PresentationPreview }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [duration, setDuration] = useState(target.module === "LISTENING" ? "600" : target.module === "WRITING" && target.taskNumber === 2 ? "2400" : "1200");
  const [pending, setPending] = useState(false);
  const [presentation, setPresentation] = useState<AttemptPresentationMode>("PRACTICE");
  const [choosing, setChoosing] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const [flow, setFlow] = useState<"GUIDED" | "FREE">("GUIDED");
  const [error, setError] = useState<string | { message: TranslationKey } | null>(null);
  const starting = useRef(false);
  const minutes = target.module === "LISTENING" ? [10, 15, 20] : target.module === "READING" ? [20, 25, 30] : [20, 25, 30, 35, 40];

  async function start() {
    if (starting.current || unavailableReason) return;
    starting.current = true;
    setPending(true);
    setError(null);
    try {
      const result = await startAttempt(target.module === "SPEAKING" ? {
        test_version_id: versionId, module: "SPEAKING", scope: "FOCUSED_UNIT",
        focused_unit: { kind: "SPEAKING_PART", id: target.unitId }, speaking_mode: "PRACTICE",
        speaking_practice_flow: target.partNumber === 2 ? "GUIDED" : flow, timer: { mode: "COUNT_UP" },
      } : {
        test_version_id: versionId, module: target.module, scope: "FOCUSED_UNIT",
        focused_unit: { kind: target.module === "READING" ? "READING_PASSAGE" : target.module === "LISTENING" ? "LISTENING_PART" : "WRITING_TASK", id: target.unitId },
        timer: duration === "count-up" ? { mode: "COUNT_UP" } : { mode: "COUNTDOWN", duration_seconds: Number(duration) },
      });
      if (target.module === "READING" || target.module === "LISTENING") rememberAttemptPresentation(result, presentation);
      router.push(`/attempt/${result.attempt_id}`);
      setChoosing(false);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "practice.startFailed" });
      starting.current = false;
      setPending(false);
    }
  }

  return <div className="practice-start mt-5 border-t border-[var(--line)] pt-4">
    {target.module === "SPEAKING" ? target.partNumber === 2 ? <p>{t("speakingPractice.guided")}</p> : <label className="field-label">{t("speakingPractice.flow")}<select className="select-field mt-2" value={flow} disabled={pending || Boolean(unavailableReason)} onChange={event => setFlow(event.target.value as "GUIDED" | "FREE")}><option value="GUIDED">{t("speakingPractice.guided")}</option><option value="FREE">{t("speakingPractice.free")}</option></select></label> : <label className="field-label">{t("practice.timer")}
      <select className="select-field mt-2" value={duration} disabled={pending || Boolean(unavailableReason)} onChange={(event) => setDuration(event.target.value)}>
        {minutes.map((minute) => <option key={minute} value={minute * 60}>{t("common.minutes", { count: minute })}</option>)}
        <option value="count-up">{t("practice.countUp")}</option>
      </select>
    </label>}
    <button ref={trigger} type="button" disabled={pending || Boolean(unavailableReason)} onClick={() => { if (target.module === "READING" || target.module === "LISTENING") setChoosing(true); else void start(); }} className={`btn mt-3 w-full ${target.module === "WRITING" ? "btn-writing" : target.module === "LISTENING" ? "btn-listening" : "btn-primary"}`}>
      {pending ? t("practice.starting") : t("practice.startFocused")}
    </button>
    {unavailableReason ? <p className="mt-3 text-sm text-[var(--muted)]">{unavailableReason}</p> : null}
    {error && !choosing ? <p role="alert" className="notice notice-error mt-3">{typeof error === "string" ? error : t(error.message)}</p> : null}
    {target.module === "READING" || target.module === "LISTENING" ? <PresentationDialog open={choosing} module={target.module} value={presentation} onChange={setPresentation} onClose={() => setChoosing(false)} onConfirm={() => void start()} pending={pending} error={typeof error === "string" ? error : error ? t(error.message) : null} returnFocusRef={trigger} preview={preview} /> : null}
  </div>;
}
