import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { getTest } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

export default async function TestDetailPage({ params }: { params: Promise<{ testId: string }> }) {
  const { testId } = await params;
  const test = await getTest(testId).catch(() => null);
  if (!test) notFound();
  return (
    <>
      <PageHeading eyebrow="Exam builder" title={test.title} description={test.description ?? "No description"} />
      <section className="surface-card overflow-hidden">
        <div className="section-header border-b border-[var(--line)] px-6 py-5">
          <div><h2 className="section-title">Versions</h2><p className="section-description">Open a draft to continue authoring, or inspect a frozen published version.</p></div>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {test.versions.map((version) => (
            <Link key={version.id} href={`/admin/tests/${test.id}/versions/${version.id}/edit`} className="group flex items-center justify-between gap-4 px-6 py-5 transition-colors hover:bg-[var(--surface-soft)]">
              <div>
                <p className="font-semibold">Version {version.version_number}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">Created {new Date(version.created_at).toLocaleString()}</p>
              </div>
              <div className="flex items-center gap-4"><StatusBadge status={version.status} /><ArrowIcon className="size-4 text-[var(--muted)] transition-transform group-hover:translate-x-1" /></div>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
