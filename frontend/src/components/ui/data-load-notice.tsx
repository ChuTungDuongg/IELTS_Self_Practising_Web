"use client";

import { useRouter } from "next/navigation";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function DataLoadNotice() {
  const router = useRouter();
  const { t } = useTranslation();
  return <div className="notice data-load-notice" role="alert">
    <span>{t("ui.partialLoad")}</span>
    <button type="button" className="btn btn-secondary" onClick={() => router.refresh()}>{t("ui.retry")}</button>
  </div>;
}
