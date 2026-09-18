import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { getTests } from "@/lib/api/tests";
import { StartAttempt } from "@/features/exam/start-attempt";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const tests = await getTests().catch(() => []);
  const available = tests.flatMap((test) =>
    test.versions
      .filter((version) => version.status === "PUBLISHED")
      .map((version) => ({ test, version })),
  );
  return (
    <>
      <PageHeading title="Test library" description="Published versions available for new attempts." />
      {available.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {available.map(({ test, version }) => (
            <article key={version.id} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5">
              <div className="flex items-start justify-between gap-3">
                <h2 className="font-semibold">{test.title}</h2>
                <StatusBadge status={version.status} />
              </div>
              <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{test.description ?? "No description"}</p>
              <Link className="mt-5 inline-block text-sm font-semibold text-[var(--accent)]" href={`/admin/tests/${test.id}`}>
                View version {version.version_number}
              </Link>
              <StartAttempt versionId={version.id} />
            </article>
          ))}
        </div>
      ) : (
        <EmptyState message="No published test versions yet." />
      )}
    </>
  );
}

function EmptyState({ message }: { message: string }) {
  return <p className="rounded-xl border border-dashed border-[var(--line)] p-8 text-center text-[var(--muted)]">{message}</p>;
}
