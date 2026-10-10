"use client";

import { useRouter } from "next/navigation";
import type { TranslationKey } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import { startTestSession } from "@/lib/api/test-sessions";

export function StartFullMock({ versionId, unavailableReason, warnings = [] }: { versionId: string; unavailableReason?: string; warnings?: string[] }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: TranslationKey }>();
  async function start() {
    setPending(true); setError(undefined);
    try {
      const result = await startTestSession(versionId);
      router.push(`/attempt/${result.current_attempt.attempt_id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "practice.mockFailed" });
      setPending(false);
    }
  }
  return <section className="full-mock-card"><div><p className="practice-module-kicker">{t("practice.fullMock")}</p><h2>{t("practice.mockOrder")}</h2><span>{t("practice.mockDescription")}</span>{warnings.map((warning, index) => <p className="notice mt-3" key={index}>{warning}</p>)}</div>{unavailableReason ? <p className="notice">{t("practice.mockUnavailable", { reason: unavailableReason })}</p> : <button type="button" className="btn btn-primary" disabled={pending} onClick={() => void start()}>{pending ? t("practice.starting") : t("practice.startMock")}</button>}{error ? <p role="alert" className="notice notice-error">{typeof error === "string" ? error : error ? t(error.message) : null}</p> : null}</section>;
}
