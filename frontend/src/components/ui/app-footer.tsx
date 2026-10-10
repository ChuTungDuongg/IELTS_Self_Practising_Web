"use client";

import type { ReactElement } from "react";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";

export function AppFooter({ year }: { year: number }): ReactElement {
  const { locale } = useLocale();
  const { t } = useTranslation();
  return <footer className="app-footer">
    <div className="app-footer-inner">
      <div><strong>IELTS Studio</strong><p>{t("footer.description")}</p></div>
      <div><p>{t("footer.copyright", { year })}</p><span lang={locale}>{t("footer.language")}</span></div>
    </div>
  </footer>;
}
