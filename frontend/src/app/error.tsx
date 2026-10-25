"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

export default function PageError({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const { t } = useTranslation();
  return <section className="workspace-error" role="alert">
    <h1>{t("ui.loadFailed")}</h1>
    <p>{t("ui.loadFailedDescription")}</p>
    <button type="button" className="btn btn-primary" onClick={retry}>{t("ui.retry")}</button>
  </section>;
}
