"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { pauseAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import { AttemptStoppedError, attemptDestination, reconcileAttemptError } from "@/features/exam/attempt-lifecycle";

export function PauseAttemptControl({
  attemptId,
  beforePause,
}: {
  attemptId: string;
  beforePause?: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [error, setError] = useState<string | { message: import("@/lib/i18n/types").TranslationKey }>();

  async function confirm() {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError(undefined);
    try {
      await beforePause?.();
      const attempt = await pauseAttempt(attemptId);
      router.push(attemptDestination(attempt));
    } catch (caught) {
      if (caught instanceof AttemptStoppedError) return;
      try {
        if (await reconcileAttemptError(caught, attemptId, (attempt) => router.push(attemptDestination(attempt)))) return;
      } catch (reconcileError) {
        caught = reconcileError;
      }
      setError(caught instanceof ApiError ? caught.message : { message: "runner.pauseError" });
      pendingRef.current = false;
      setPending(false);
    }
  }

  return (
    <>
      <button type="button" className="exam-pause-button" onClick={() => setOpen(true)}>
        {t("runner.pauseExit")}
      </button>
      <ConfirmDialog
        open={open}
        title={t("runner.pauseTitle")}
        description={t("runner.pauseDescription")}
        confirmLabel={t("runner.pauseExit")}
        pending={pending}
        errorMessage={typeof error === "string" ? error : error ? t(error.message) : undefined}
        onCancel={() => { setOpen(false); setError(undefined); }}
        onConfirm={() => void confirm()}
      />
    </>
  );
}
