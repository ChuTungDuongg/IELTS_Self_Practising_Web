import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { getHistory } from "@/lib/api/history";
import { getTests } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [tests, history] = await Promise.all([
    getTests().catch(() => []),
    getHistory().catch(() => ({ items: [], total: 0 })),
  ]);
  const published = tests.flatMap((test) => test.versions).filter((item) => item.status === "PUBLISHED");
  const inProgress = history.items.filter((item) => item.status === "IN_PROGRESS");

  return (
    <>
      <PageHeading
        eyebrow="Local study workspace"
        title="Build thoughtfully. Practice with focus."
        description="Your private IELTS studio for structured test authoring, frozen published versions, and server-saved practice attempts."
      />
      <section className="grid gap-5 sm:grid-cols-3" aria-label="Workspace summary">
        {[
          ["Published versions", String(published.length), "/library"],
          ["Active attempts", String(inProgress.length), "/history"],
          ["Tests in builder", String(tests.length), "/admin/tests"],
        ].map(([label, value, href]) => (
          <Link key={label} href={href} className="surface-card group relative overflow-hidden p-6 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-md)]">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-blue-600 to-cyan-400 opacity-80" />
            <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">{label}</p>
            <p className="mt-4 text-4xl font-bold tracking-tight">{value}</p>
            <p className="mt-3 text-xs font-semibold text-[var(--accent)]">View workspace →</p>
          </Link>
        ))}
      </section>
      <section className="surface-card mt-8 overflow-hidden p-7">
        <div className="max-w-3xl"><p className="page-eyebrow">Workspace foundation</p><h2 className="section-title">Reliable authoring from draft to review</h2>
        <p className="mt-3 leading-7 text-[var(--muted)]">Test metadata, immutable publishing, attempts, timers, history, and asset boundaries work together so the authoring flow stays flexible without compromising past results.</p></div>
      </section>
    </>
  );
}
