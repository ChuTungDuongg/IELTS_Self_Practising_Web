import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { getTests } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

export default async function AdminTestsPage() {
  const tests = await getTests().catch(() => []);
  return (
    <>
      <PageHeading
        eyebrow="Exam builder"
        title="Tests"
        description="Create logical tests, then publish immutable versions when their module content is valid."
        action={<Link href="/admin/tests/new" className="rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--accent-strong)]">New test</Link>}
      />
      <div className="space-y-3">
        {tests.map((test) => (
          <Link key={test.id} href={`/admin/tests/${test.id}`} className="flex items-center gap-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5 hover:border-[#9eb8ae]">
            <div className="min-w-0 flex-1">
              <h2 className="truncate font-semibold">{test.title}</h2>
              <p className="mt-1 text-sm text-[var(--muted)]">{test.versions.length} version{test.versions.length === 1 ? "" : "s"}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {test.versions.slice(-3).map((version) => <StatusBadge key={version.id} status={version.status} />)}
            </div>
          </Link>
        ))}
        {!tests.length ? <p className="rounded-xl border border-dashed border-[var(--line)] p-8 text-center text-[var(--muted)]">No tests yet. Create the first draft.</p> : null}
      </div>
    </>
  );
}
