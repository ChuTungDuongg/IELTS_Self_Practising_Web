"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import { GravityLanding } from "./gravity/gravity-landing";
import { ArrowIcon, BuilderIcon, HeadphonesIcon, HistoryIcon, LibraryIcon, ReadingIcon, SparkleIcon } from "@/components/ui/icons";
import { AdminOnly } from "@/features/auth/admin-only";
import type { AdminStats } from "@/lib/api/admin";
import type { Profile } from "@/lib/api/profile";
import type { HistoryItem } from "@/lib/api/history";
import { formatProjectDate } from "@/lib/date-time";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { GoalCountdown } from "./goal-countdown";

export function OverviewContent({ publishedCount, resumableCount, testCount, isAdmin, adminStats, profile, recentAttempt, signedIn = true }: { publishedCount: number; resumableCount: number; testCount: number; isAdmin: boolean; adminStats: AdminStats | null; profile: Profile | null; recentAttempt?: Pick<HistoryItem, "attempt_id" | "test_title" | "module" | "status">; signedIn?: boolean }): ReactElement {
  const { t } = useTranslation();
  const pathways = [
    { title: t("pages.overview.tests"), description: t("pages.overview.testsDescription"), href: "/library", eyebrow: t("pages.overview.practiceLibrary"), icon: LibraryIcon, tone: "indigo" },
    { title: t("pages.overview.reading"), description: t("pages.overview.readingDescription"), href: "/practice?skill=READING", eyebrow: t("pages.overview.editorialFocus"), icon: ReadingIcon, tone: "cyan" },
    { title: t("pages.overview.listening"), description: t("pages.overview.listeningDescription"), href: "/practice?skill=LISTENING", eyebrow: t("pages.overview.guidedAudio"), icon: HeadphonesIcon, tone: "violet" },
    { title: t("pages.overview.progress"), description: t("pages.overview.progressDescription"), href: "/history", eyebrow: t("pages.overview.practiceRecord"), icon: HistoryIcon, tone: "blue" },
  ] as const;

  return (
    <div className="home-page gravity-home">
      <GravityLanding recentAttempt={recentAttempt} />
      <div id="study-workspace" className="home-workspace">
      <div className="section-header"><div><h2 className="section-title">{t("gravity.workspace")}</h2><p className="section-description">{t("gravity.workspaceDescription")}</p></div><AdminOnly><Link href="/admin/tests" prefetch={false} className="btn btn-secondary"><BuilderIcon className="size-4" />{t("pages.overview.builderAction")}</Link></AdminOnly></div>
      {signedIn ? <section className={`home-metrics${isAdmin ? " home-metrics-admin" : ""}`} aria-label={t("pages.overview.summary")}>
        {[
          [t("pages.overview.published"), String(publishedCount), t("pages.overview.ready"), "/library"],
          [t("pages.overview.resumable"), String(resumableCount), t("pages.overview.saved"), "/history"],
        ].map(([label, value, detail, href]) => (
          <Link key={href} href={href} className="home-metric">
            <span className="home-metric-value">{value}</span>
            <span><strong>{label}</strong><small>{detail}</small></span>
            <ArrowIcon className="size-4" />
          </Link>
        ))}
        {isAdmin ? <Link href="/admin/tests" className="home-metric"><span className="home-metric-value">{testCount}</span><span><strong>{t("pages.overview.builderTests")}</strong><small>{t("pages.overview.authoring")}</small></span><ArrowIcon className="size-4" /></Link> : null}
        {adminStats ? <Link href="/admin" className="home-metric"><span className="home-metric-value">{adminStats.total_users}</span><span><strong>{t("pages.overview.users")}</strong><small>{t("pages.overview.activeUsers", { count: adminStats.active_users })}</small></span><ArrowIcon className="size-4" /></Link> : null}
      </section> : <section className="surface-card home-guest"><h3>{t("gravity.guestTitle")}</h3><p>{t("gravity.guestDescription")}</p><div className="gravity-actions"><Link href="/login" prefetch={false} className="btn btn-primary">{t("shell.login")}</Link><Link href="/register" prefetch={false} className="btn btn-secondary">{t("shell.register")}</Link></div></section>}

      {profile ? <IeltsGoals profile={profile} /> : null}

      <section className="home-learning" aria-labelledby="learning-paths-title">
        <div className="section-header">
          <div><p className="page-eyebrow">{t("pages.overview.paths")}</p><h2 id="learning-paths-title" className="section-title">{t("pages.overview.choose")}</h2><p className="section-description">{t("pages.overview.pathsDescription")}</p></div>
          <Link href="/library" className="btn btn-ghost">{t("pages.overview.explore")} <ArrowIcon className="size-4" /></Link>
        </div>
        <div className="learning-path-grid">
          {pathways.map(({ title, description, href, eyebrow, icon: Icon, tone }) => (
            <Link key={tone} href={href} className={`learning-path-card learning-path-${tone}`}>
              <span className="learning-path-icon"><Icon className="size-6" /></span>
              <span className="learning-path-copy"><small>{eyebrow}</small><strong>{title}</strong><span>{description}</span></span>
              <ArrowIcon className="learning-path-arrow size-4" />
            </Link>
          ))}
        </div>
      </section>

      <section className="home-foundation">
        <span className="home-foundation-mark" aria-hidden="true"><SparkleIcon /></span>
        <div><p className="page-eyebrow">{t("pages.overview.continuity")}</p><h2 className="section-title">{t("pages.overview.reliable")}</h2><p>{t("pages.overview.foundation")}</p></div>
        <Link href="/history" className="btn btn-secondary">{t("pages.overview.progressAction")}</Link>
      </section>
      </div>
    </div>
  );
}

function IeltsGoals({ profile }: { profile: Profile }) {
  const { t } = useTranslation();
  const skills = [
    ["pages.overview.listeningTarget", profile.target_listening_band],
    ["pages.overview.readingTarget", profile.target_reading_band],
    ["pages.overview.writingTarget", profile.target_writing_band],
    ["pages.overview.speakingTarget", profile.target_speaking_band],
  ] as const;
  const hasGoals = profile.target_band !== null || skills.some(([, value]) => value !== null) || profile.target_test_date !== null;

  return <section className={`surface-card home-goals${hasGoals ? "" : " home-goals-empty"}`} aria-labelledby="home-goals-title">
    {hasGoals ? <>
      <div className="home-goals-heading"><p className="page-eyebrow">{t("pages.overview.personal")}</p><h2 id="home-goals-title" className="section-title">{t("pages.overview.goals")}</h2></div>
      <div className="home-goals-body">
        <div className="home-goals-overall"><span>{t("pages.overview.overall")}</span><strong>{formatTarget(profile.target_band)}</strong></div>
        <div className="home-goals-skills">
          {skills.map(([label, value]) => <div className="home-goals-skill" key={label}><span>{t(label)}</span><strong>{formatTarget(value)}</strong></div>)}
        </div>
      </div>
      {profile.target_test_date ? <GoalCountdown date={profile.target_test_date} /> : null}
      <div className="home-goals-footer"><p>{t("pages.overview.targetTest")} <strong>{profile.target_test_date ? formatProjectDate(profile.target_test_date) : "—"}</strong></p><Link href="/profile" className="btn btn-ghost">{t("pages.overview.editGoals")} <ArrowIcon className="size-4" /></Link></div>
    </> : <>
      <div><p className="page-eyebrow">{t("pages.overview.personal")}</p><h2 id="home-goals-title" className="section-title">{t("pages.overview.emptyGoal")}</h2><p className="section-description">{t("pages.overview.goalDescription")}</p></div>
      <Link href="/profile" className="btn btn-secondary">{t("pages.overview.setGoals")} <ArrowIcon className="size-4" /></Link>
    </>}
  </section>;
}

function formatTarget(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}
