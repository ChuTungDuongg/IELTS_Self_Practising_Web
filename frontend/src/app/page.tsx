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
        title="Practice with focus. Build with confidence."
        description="A private IELTS computer-test workspace backed by frozen test versions and server-saved attempts."
      />
      <section className="grid gap-4 sm:grid-cols-3" aria-label="Workspace summary">
        {[
          ["Published versions", String(published.length), "/library"],
          ["Active attempts", String(inProgress.length), "/history"],
          ["Tests in builder", String(tests.length), "/admin/tests"],
        ].map(([label, value, href]) => (
          <Link key={label} href={href} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5 hover:border-[#9eb8ae]">
            <p className="text-sm text-[var(--muted)]">{label}</p>
            <p className="mt-3 text-3xl font-semibold">{value}</p>
          </Link>
        ))}
      </section>
      <section className="mt-10 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6">
        <h2 className="text-lg font-semibold">Phase 1 foundation</h2>
        <p className="mt-2 max-w-3xl leading-7 text-[var(--muted)]">
          Test metadata, immutable publishing, attempts, timers, history, and asset boundaries are ready.
          Reading authoring and the split-pane exam runner arrive in Phase 2.
        </p>
      </section>
    </>
  );
}
