"use client";

import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationKey } from "@/lib/i18n/types";

export function DataLoadNotice({ message = "ui.partialLoad" }: { message?: TranslationKey } = {}) {
  const router = useRouter();
  const { t } = useTranslation();
  return <div className="notice data-load-notice" role="alert">
    <span>{t(message)}</span>
    <button type="button" className="btn btn-secondary" onClick={() => router.refresh()}>{t("ui.retry")}</button>
  </div>;
}
