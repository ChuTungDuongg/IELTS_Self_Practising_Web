import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { getTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";
import { formatProjectDateTime } from "@/lib/date-time";

export const dynamic = "force-dynamic";

export default async function TestDetailPage({ params, searchParams }: { params: Promise<{ testId: string }>; searchParams?: Promise<{ builder?: string }> }) {
  const { testId } = await params;
  const builderState = (await searchParams)?.builder;
  const test = await getTest(testId).catch(() => null);
  if (!test) notFound();
  return (
    <>
      <PageHeading eyebrow="Exam builder" title={test.title} description={test.description ?? "No description"} />
      {builderState === "version-unavailable" ? <p role="status" className="notice mb-5">That version is no longer available. Choose a current version below.</p> : null}
      <section className="version-library surface-card overflow-hidden">
        <div className="section-header border-b border-[var(--line)] px-6 py-5">
          <div><h2 className="section-title">Versions</h2><p className="section-description">Open a draft to continue authoring, or inspect a frozen published version.</p></div>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {test.versions.map((version) => (
            <Link key={version.id} href={builderEditPath(test.id, version.id)} className="version-row group">
              <div>
                <p className="font-semibold">Version {version.version_number} · {version.status === "PUBLISHED" ? "Current published" : version.status === "DRAFT" ? "Draft" : "Historical"}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">Created {formatProjectDateTime(version.created_at)}</p>
              </div>
              <div className="flex items-center gap-4"><StatusBadge status={version.status} /><ArrowIcon className="size-4 text-[var(--muted)] transition-transform group-hover:translate-x-1" /></div>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
