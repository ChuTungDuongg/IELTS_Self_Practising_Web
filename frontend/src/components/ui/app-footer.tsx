"use client";

import { useState, type ReactElement } from "react";
import Link from "next/link";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";

export function AppFooter({ year, home = false }: { year: number; home?: boolean }): ReactElement {
  const { locale } = useLocale();
  const { t } = useTranslation();
  const [motion, setMotion] = useState<"playing" | "paused">("playing");
  const paused = motion === "paused";
  return <footer className={`app-footer${home ? " gravity-footer" : ""}`} data-motion={motion} data-motion-paused={paused}>
    {home ? <>
      <div className="gravity-footer-ticker" aria-hidden="true">
        <div>{[0, 1].map(repeat => <span key={repeat}>
          {t("gravity.ticker")}<i />{t("gravity.tickerTwo")}<i />
          {t("gravity.ticker")}<i />{t("gravity.tickerTwo")}<i />
        </span>)}</div>
      </div>
      <div className="gravity-footer-top">
        <h2>{t("gravity.footerTitle")}</h2>
        <div>
          <Link href="/practice" prefetch={false}>{t("shell.practice")} ↗</Link>
          <Link href="/library" prefetch={false}>{t("shell.library")} ↗</Link>
          <Link href="/history" prefetch={false}>{t("shell.history")} ↗</Link>
          <Link href="/analytics" prefetch={false}>{t("shell.analytics")} ↗</Link>
        </div>
      </div>
      <div className="gravity-footer-signature">
        <p className="gravity-wordmark" aria-hidden="true">BandPilot</p>
        <button type="button" className="gravity-footer-pause" aria-pressed={paused} onClick={() => setMotion(paused ? "playing" : "paused")}>
          <span aria-hidden="true">{paused ? "▶" : "Ⅱ"}</span>
          {t(paused ? "gravity.playTicker" : "gravity.pauseTicker")}
        </button>
      </div>
    </> : null}
    <div className="app-footer-inner">
      <div><strong>BandPilot</strong><p lang="en">{t("footer.tagline")}</p><p>{t("footer.description")}</p></div>
      <div><p>{t("footer.copyright", { year })}</p><span lang={locale}>{t("footer.language")}</span></div>
    </div>
  </footer>;
}
