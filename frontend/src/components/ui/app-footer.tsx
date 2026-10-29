"use client";

import { useState, type ReactElement } from "react";
import Link from "next/link";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { LoopingTicker } from "./looping-ticker";
import { FooterContacts } from "./footer-contacts";
import { GravityMotionControls } from "@/components/home/gravity/gravity-motion-controls";
import { FooterIcon } from "./footer-icon";

export function AppFooter({ year, home = false }: { year: number; home?: boolean }): ReactElement {
  const { locale } = useLocale();
  const { t } = useTranslation();
  const [motion, setMotion] = useState<"playing" | "paused">("playing");
  const paused = motion === "paused";
  return <footer className={`app-footer${home ? " gravity-footer" : ""}`} data-motion={motion} data-motion-paused={paused}>
    {home ? <>
      <LoopingTicker>{t("gravity.ticker")}<i />{t("gravity.tickerTwo")}<i /></LoopingTicker>
      <div className="gravity-footer-top">
        <div className="gravity-footer-signature">
          <div className="gravity-footer-atmosphere" aria-hidden="true">
            <span className="gravity-footer-orbit" />
            <span className="gravity-footer-sphere gravity-footer-sphere-indigo" />
            <span className="gravity-footer-sphere gravity-footer-sphere-blue" />
            <span className="gravity-footer-sphere gravity-footer-sphere-small" />
          </div>
          <h2>{t("gravity.footerTitle")}</h2>
          <p className="gravity-wordmark" aria-hidden="true">BandPilot</p>
          <div className="gravity-footer-copy"><p lang="en">{t("footer.tagline")}</p><p>{t("footer.description")}</p></div>
        </div>
        <div className="gravity-footer-side">
          <div className="gravity-footer-navigation">
            <Link href="/practice" prefetch={false}>{t("shell.practice")} ↗</Link>
            <Link href="/library" prefetch={false}>{t("shell.library")} ↗</Link>
            <Link href="/history" prefetch={false}>{t("shell.history")} ↗</Link>
            <Link href="/analytics" prefetch={false}>{t("shell.analytics")} ↗</Link>
          </div>
          <div className="gravity-footer-controls">
            <GravityMotionControls />
            <button type="button" className="gravity-footer-pause" aria-pressed={paused} onClick={() => setMotion(paused ? "playing" : "paused")}>
              <FooterIcon name={paused ? "play" : "pause"} />
              {t(paused ? "gravity.playTicker" : "gravity.pauseTicker")}
            </button>
          </div>
        </div>
      </div>
    </> : null}
    <div className={`app-footer-inner${home ? " gravity-footer-bottom" : ""}`}>
      {!home ? <div><strong>BandPilot</strong><p lang="en">{t("footer.tagline")}</p><p>{t("footer.description")}</p></div> : null}
      <FooterContacts showcase={home} />
      <div className="footer-legal"><p>{t("footer.copyright", { year })}</p><span lang={locale}>{t("footer.language")}</span></div>
    </div>
  </footer>;
}
