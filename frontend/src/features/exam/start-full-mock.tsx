"use client";

import { useRouter } from "next/navigation";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { startTestSession } from "@/lib/api/test-sessions";
import { rememberSessionPresentation, type AttemptPresentationMode } from "./attempt-presentation";
import { PresentationDialog } from "./presentation-dialog";
import type { PresentationPreview } from "./presentation-thumbnail";

export function StartFullMock({ versionId, unavailableReason, warnings = [], preview }: { versionId: string; unavailableReason?: string; warnings?: string[]; preview?: PresentationPreview }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [pending, setPending] = useState(false);
  const [presentation, setPresentation] = useState<AttemptPresentationMode>("PRACTICE");
  const [choosing, setChoosing] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const starting = useRef(false);
  const [error, setError] = useState<string | { message: TranslationKey }>();
  async function start() {
    if (starting.current) return;
    starting.current = true;
    setPending(true); setError(undefined);
    try {
      const result = await startTestSession(versionId);
      rememberSessionPresentation(result.session.session_id, presentation);
      router.push(`/attempt/${result.current_attempt.attempt_id}`);
      setChoosing(false);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "practice.mockFailed" });
      setPending(false);
      starting.current = false;
    }
  }
  return <section className="practice-full-mock-strip">
    <div className="practice-full-mock-copy">
      <p className="practice-full-mock-title">{t("practice.fullMock")}</p>
      <h2>{t("practice.mockOrder")}</h2>
      <span className="practice-full-mock-helper">{t("practice.mockDescription")}</span>
      {warnings.map((warning, index) => <p className="notice mt-3" key={index}>{warning}</p>)}
    </div>
    <div className="practice-full-mock-action">
      {unavailableReason ? <p className="notice">{t("practice.mockUnavailable", { reason: unavailableReason })}</p> : <button ref={trigger} type="button" className="btn btn-primary" disabled={pending} onClick={() => setChoosing(true)}>{pending ? t("practice.starting") : t("practice.startMock")}</button>}
    </div>
    {error && !choosing ? <p role="alert" className="notice notice-error">{typeof error === "string" ? error : t(error.message)}</p> : null}
    <PresentationDialog open={choosing} module="LISTENING" value={presentation} onChange={setPresentation} onClose={() => setChoosing(false)} onConfirm={() => void start()} pending={pending} error={typeof error === "string" ? error : error ? t(error.message) : null} returnFocusRef={trigger} preview={preview} />
  </section>;
}
