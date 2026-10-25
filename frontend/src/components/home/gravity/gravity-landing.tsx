"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowIcon } from "@/components/ui/icons";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { HistoryItem } from "@/lib/api/history";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { GravityField } from "./gravity-field";

type RecentAttempt = Pick<HistoryItem, "attempt_id" | "test_title" | "module" | "status">;
const skills = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;

export function GravityLanding({ recentAttempt }: { recentAttempt?: RecentAttempt }) {
  const { t } = useTranslation();
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = root.current;
    if (!element || typeof IntersectionObserver === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) {
        entry.target.classList.add("gravity-revealed"); observer.unobserve(entry.target);
      }
    }, { threshold: .25 });
    // Content is visible by default. Add motion only when a supported observer is ready.
    element.querySelectorAll<HTMLElement>("[data-reveal]").forEach(node => { node.classList.add("gravity-reveal-enabled"); observer.observe(node); });
    return () => { observer.disconnect(); element.querySelectorAll(".gravity-reveal-enabled").forEach(node => node.classList.remove("gravity-reveal-enabled")); };
  }, []);

  return <div ref={root} className="gravity-story" data-stage="0">
    <GravityField />
    <section className="gravity-section gravity-hero" data-gravity-section aria-labelledby="gravity-title">
      <div className="gravity-hero-copy">
        <p className="gravity-label">{t("gravity.eyebrow")}</p>
        <h1 id="gravity-title">{t("gravity.heroOne")}<br />{t("gravity.heroTwo")}</h1>
        <div className="gravity-hero-bottom">
          <div><p className="gravity-description">{t("gravity.heroDescription")}</p><div className="gravity-actions"><Link href="/practice" prefetch={false} className="gravity-cta">{t("pages.overview.start")}<span aria-hidden="true"><ArrowIcon /></span></Link><a href="#study-workspace" className="gravity-text-link">{t("gravity.workspace")}</a></div></div>
          {recentAttempt ? <div className="gravity-resume"><p>{t("ui.continuePractice")} · {t(moduleTranslationKeys[recentAttempt.module])}</p><h2>{recentAttempt.test_title}</h2><Link href={recentAttempt.status === "PAUSED" ? "/history" : `/attempt/${recentAttempt.attempt_id}`} prefetch={false} className="gravity-text-link">{t("ui.continueSaved")} <ArrowIcon /></Link></div> : <p className="gravity-scroll-cue"><span aria-hidden="true">↓</span>{t("gravity.scroll")}</p>}
        </div>
      </div>
    </section>
    <section className="gravity-section gravity-skills" data-gravity-section aria-labelledby="gravity-skills-title">
      <div className="gravity-section-intro"><p className="gravity-label" data-reveal>{t("gravity.skillsLabel")}</p><h2 id="gravity-skills-title" data-reveal>{t("gravity.skillsTitle")}</h2><p className="gravity-description" data-reveal>{t("gravity.skillsDescription")}</p></div>
      <div className="gravity-skill-list">{skills.map((skill, index) => <Link key={skill} href={`/practice?skill=${skill}`} prefetch={false} data-reveal style={{ "--reveal-delay": `${index * 80}ms` } as React.CSSProperties}><span><strong>{t(moduleTranslationKeys[skill])}</strong><small>{t(`gravity.skill.${skill}`)}</small></span><ArrowIcon aria-hidden="true" /></Link>)}</div>
    </section>
    <section className="gravity-section gravity-shape" data-gravity-section aria-labelledby="gravity-shape-title">
      <div><p className="gravity-label" data-reveal>{t("gravity.reviewLabel")}</p><h2 id="gravity-shape-title" data-reveal>{t("gravity.reviewTitle")}</h2></div>
      <div className="gravity-shape-copy"><p className="gravity-description" data-reveal>{t("gravity.reviewDescription")}</p><Link href="/history" prefetch={false} className="gravity-text-link" data-reveal>{t("gravity.reviewAction")} <ArrowIcon /></Link></div>
    </section>
    <section className="gravity-section gravity-release" data-gravity-section aria-labelledby="gravity-release-title">
      <p className="gravity-label" data-reveal>{t("gravity.mockLabel")}</p><h2 id="gravity-release-title" data-reveal>{t("gravity.mockOne")}<br />{t("gravity.mockTwo")}</h2><p className="gravity-description" data-reveal>{t("gravity.mockDescription")}</p><Link href="/library" prefetch={false} className="gravity-cta" data-reveal>{t("gravity.mockAction")}<span aria-hidden="true"><ArrowIcon /></span></Link>
    </section>
  </div>;
}
