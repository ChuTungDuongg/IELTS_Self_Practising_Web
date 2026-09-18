import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { getTest } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

export default async function TestDetailPage({ params }: { params: Promise<{ testId: string }> }) {
  const { testId } = await params;
  const test = await getTest(testId).catch(() => null);
  if (!test) notFound();
  return (
    <>
      <PageHeading eyebrow="Exam builder" title={test.title} description={test.description ?? "No description"} />
      <section>
        <h2 className="mb-3 text-lg font-semibold">Versions</h2>
        <div className="space-y-3">
          {test.versions.map((version) => (
            <Link key={version.id} href={`/admin/tests/${test.id}/versions/${version.id}/edit`} className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5 hover:border-[#9eb8ae]">
              <div>
                <p className="font-medium">Version {version.version_number}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">Created {new Date(version.created_at).toLocaleString()}</p>
              </div>
              <StatusBadge status={version.status} />
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
