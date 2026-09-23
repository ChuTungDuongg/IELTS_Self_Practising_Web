import Link from "next/link";
import { InteractivePlanet } from "@/components/home/interactive-planet";
import { ArrowIcon, BuilderIcon, HeadphonesIcon, HistoryIcon, LibraryIcon, ReadingIcon, SparkleIcon } from "@/components/ui/icons";
import { getHistory } from "@/lib/api/history";
import { getTests } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import { AdminOnly } from "@/features/auth/admin-only";
import { getAdminStats } from "@/lib/api/admin";
import { userSchema } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { getProfile, type Profile } from "@/lib/api/profile";
import { formatProjectDate } from "@/lib/date-time";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [tests, history, user] = await Promise.all([
    getTests(undefined, serverApiRequest).catch(() => []),
    getHistory(serverApiRequest).catch(() => ({ items: [], groups: [], total: 0 })),
    getHomepageUser(),
  ]);
  const [adminStats, profile] = await Promise.all([
    user?.role === "ADMIN" ? getAdminStats(serverApiRequest) : null,
    user ? getHomepageProfile() : null,
  ]);
  const published = tests.flatMap((test) => test.versions).filter((item) => item.status === "PUBLISHED");
  const inProgress = history.items.filter((item) => item.status === "IN_PROGRESS" || item.status === "PAUSED");
  const pathways = [
    { title: "IELTS Tests", description: "Choose a frozen published test and begin a focused practice session.", href: "/library", eyebrow: "Practice library", icon: LibraryIcon, tone: "indigo" },
    { title: "Reading", description: "Work through passages in a calm split-pane exam experience.", href: "/library", eyebrow: "Editorial focus", icon: ReadingIcon, tone: "cyan" },
    { title: "Listening", description: "Practice with shared audio controls and structured question groups.", href: "/library", eyebrow: "Guided audio", icon: HeadphonesIcon, tone: "violet" },
    { title: "History & progress", description: "Continue active attempts or revisit submitted work and feedback.", href: "/history", eyebrow: "Practice record", icon: HistoryIcon, tone: "blue" },
  ] as const;

  return (
    <div className="home-page">
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-hero-content">
          <p className="page-eyebrow"><SparkleIcon className="size-4" /> IELTS Studio · Your learning observatory</p>
          <h1 id="home-title">Build thoughtfully.<br /><span>Practice with focus.</span></h1>
          <p className="home-hero-description">A private IELTS workspace where structured authoring, calm exam practice, and meaningful review stay connected from first draft to final answer.</p>
          <div className="home-hero-actions">
            <Link href="/library" className="btn btn-primary">Start practicing <ArrowIcon className="size-4" /></Link>
            <AdminOnly><Link href="/admin/tests" className="btn btn-secondary"><BuilderIcon className="size-4" /> Open Builder</Link></AdminOnly>
          </div>
        </div>
        <InteractivePlanet />
      </section>

      <section className={`home-metrics${user?.role === "ADMIN" ? " home-metrics-admin" : ""}`} aria-label="Workspace summary">
        {[
          ["Published", String(published.length), "Ready to practice", "/library"],
          ["Resumable", String(inProgress.length), "Saved attempts", "/history"],
        ].map(([label, value, detail, href]) => (
          <Link key={label} href={href} className="home-metric">
            <span className="home-metric-value">{value}</span>
            <span><strong>{label}</strong><small>{detail}</small></span>
            <ArrowIcon className="size-4" />
          </Link>
        ))}
        {user?.role === "ADMIN" ? <Link href="/admin/tests" className="home-metric"><span className="home-metric-value">{tests.length}</span><span><strong>Builder tests</strong><small>Authoring workspace</small></span><ArrowIcon className="size-4" /></Link> : null}
        {adminStats ? <Link href="/admin" className="home-metric"><span className="home-metric-value">{adminStats.total_users}</span><span><strong>Users</strong><small>{adminStats.active_users} active</small></span><ArrowIcon className="size-4" /></Link> : null}
      </section>

      {profile ? <IeltsGoals profile={profile} /> : null}

      <section className="home-learning" aria-labelledby="learning-paths-title">
        <div className="section-header">
          <div><p className="page-eyebrow">Learning pathways</p><h2 id="learning-paths-title" className="section-title">Choose where to continue</h2><p className="section-description">Everything you need to build, practice, and review—without losing your place.</p></div>
          <Link href="/library" className="btn btn-ghost">Explore all tests <ArrowIcon className="size-4" /></Link>
        </div>
        <div className="learning-path-grid">
          {pathways.map(({ title, description, href, eyebrow, icon: Icon, tone }) => (
            <Link key={title} href={href} className={`learning-path-card learning-path-${tone}`}>
              <span className="learning-path-icon"><Icon className="size-6" /></span>
              <span className="learning-path-copy"><small>{eyebrow}</small><strong>{title}</strong><span>{description}</span></span>
              <ArrowIcon className="learning-path-arrow size-4" />
            </Link>
          ))}
        </div>
      </section>

      <section className="home-foundation">
        <span className="home-foundation-mark" aria-hidden="true"><SparkleIcon /></span>
        <div><p className="page-eyebrow">Built for continuity</p><h2 className="section-title">Reliable from draft to review</h2><p>Published versions remain frozen, attempts stay tied to their exact source, and every saved response is ready when you return.</p></div>
        <Link href="/history" className="btn btn-secondary">View progress</Link>
      </section>
    </div>
  );
}

async function getHomepageProfile() {
  try {
    return await getProfile(serverApiRequest);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

function IeltsGoals({ profile }: { profile: Profile }) {
  const skills = [
    ["Listening", profile.target_listening_band],
    ["Reading", profile.target_reading_band],
    ["Writing", profile.target_writing_band],
    ["Speaking", profile.target_speaking_band],
  ] as const;
  const hasGoals = profile.target_band !== null || skills.some(([, value]) => value !== null) || profile.target_test_date !== null;

  return <section className={`surface-card home-goals${hasGoals ? "" : " home-goals-empty"}`} aria-labelledby="home-goals-title">
    {hasGoals ? <>
      <div className="home-goals-heading"><p className="page-eyebrow">Personal targets</p><h2 id="home-goals-title" className="section-title">IELTS goals</h2></div>
      <div className="home-goals-body">
        <div className="home-goals-overall"><span>Overall target band</span><strong>{formatTarget(profile.target_band)}</strong></div>
        <div className="home-goals-skills">
          {skills.map(([label, value]) => <div className="home-goals-skill" key={label}><span>{label} target</span><strong>{formatTarget(value)}</strong></div>)}
        </div>
      </div>
      <div className="home-goals-footer"><p>Target test <strong>{profile.target_test_date ? formatProjectDate(profile.target_test_date) : "—"}</strong></p><Link href="/profile" className="btn btn-ghost">Edit goals <ArrowIcon className="size-4" /></Link></div>
    </> : <>
      <div><p className="page-eyebrow">Personal targets</p><h2 id="home-goals-title" className="section-title">Set your IELTS goal</h2><p className="section-description">Add target bands for each skill to keep your practice focused.</p></div>
      <Link href="/profile" className="btn btn-secondary">Set goals <ArrowIcon className="size-4" /></Link>
    </>}
  </section>;
}

function formatTarget(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

async function getHomepageUser() {
  try {
    return userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
