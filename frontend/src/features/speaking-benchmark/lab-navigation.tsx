"use client";

import Link from "next/link";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { useEffect, useRef, type MouseEvent } from "react";
import styles from "./navigation.module.css";
import { LabGuide } from "./lab-guide";

const root = "/admin/speaking-benchmark";
const sections = [
  { id: "recordings", href: root, label: "speakingUx.recordings" },
  { id: "evaluation", href: `${root}/reports`, label: "speakingEval.title" },
  { id: "research", href: `${root}/research`, label: "speakingUx.research" },
  { id: "quality", href: `${root}/quality`, label: "speakingUx.qualityRelease" },
] as const;
const quality = [
  { href: `${root}/quality`, label: "speakingLab.quality" },
  { href: `${root}/suites`, label: "speakingLab.suites" },
  { href: `${root}/gates`, label: "speakingLab.gates" },
] as const;

export function LabNavigation({ current, tool, onNavigate, onSelectNavigate }: {
  current: typeof sections[number]["id"] | "reviewer";
  tool?: "quality" | "suites" | "gates";
  onNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void;
  onSelectNavigate?: (href: string) => void;
}) {
  const { t } = useTranslation();
  const utilities = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    function dismiss(event: globalThis.MouseEvent) {
      if (utilities.current?.open && !utilities.current.contains(event.target as Node)) utilities.current.open = false;
    }
    document.addEventListener("click", dismiss);
    return () => document.removeEventListener("click", dismiss);
  }, []);
  return <div className={styles.navigation} data-speaking-navigation>
    <label className={styles.mobileLab}><span className="sr-only">{t("speakingUx.labNavigation")}</span>
      <select className="field" value={current} onChange={event => {
        const href = sections.find(section => section.id === event.target.value)?.href;
        if (href) { if (onSelectNavigate) onSelectNavigate(href); else window.location.assign(href); }
      }}>
        {current === "reviewer" && <option value="reviewer" disabled>{t("speakingUx.myAssignments")}</option>}
        {sections.map(section => <option key={section.id} value={section.id}>{t(section.label)}</option>)}
      </select>
    </label>
    <nav aria-label={t("speakingUx.labNavigation")} className={styles.primary}>
      {sections.map(section => <Link key={section.id} href={section.href} prefetch={false} onClick={onNavigate} aria-current={current === section.id ? "page" : undefined}>{t(section.label)}</Link>)}
      <details ref={utilities} className={styles.utilities} onKeyDown={event => {
        if (event.key === "Escape" && utilities.current?.open) { utilities.current.open = false; utilities.current.querySelector("summary")?.focus(); }
      }}>
        <summary>{t("speakingUx.more")}</summary>
        <div className={styles.utilityLinks}>
          <Link href={`${root}/reviewer`} onClick={onNavigate} aria-current={current === "reviewer" ? "page" : undefined}>{t("speakingUx.myAssignments")}</Link>
          <Link href="/admin/writing-benchmark" onClick={onNavigate}>{t("benchmark.title")}</Link>
        </div>
      </details>
    </nav>
    {current === "quality" && <nav className={styles.secondary} aria-label={t("speakingUx.qualityRelease")}>
      {quality.map(item => <Link key={item.href} href={item.href} onClick={onNavigate} aria-current={item.href === `${root}/${tool ?? "quality"}` ? "page" : undefined}>{t(item.label)}</Link>)}
    </nav>}
    {current === "reviewer" && <nav className={styles.secondary} aria-label={t("speakingUx.myAssignments")}><Link href={`${root}/reviewer`} onClick={onNavigate}>{t("speakingUx.myAssignments")}</Link></nav>}
    <LabGuide mode={current === "evaluation" ? "reports" : current === "reviewer" ? "reviewer" : "workflow"} />
  </div>;
}
