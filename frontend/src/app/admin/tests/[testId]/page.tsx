import { UiText } from "@/lib/i18n/locale-provider";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { getTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";
import { formatProjectDateTime } from "@/lib/date-time";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function TestDetailPage({ params, searchParams }: { params: Promise<{ testId: string }>; searchParams?: Promise<{ builder?: string }> }) {
  const { testId } = await params;
  const builderState = (await searchParams)?.builder;
  const test = await getTest(testId, serverApiRequest).catch(() => null);
  if (!test) notFound();
  return (
    <>
      <PageHeading eyebrow={<UiText message="builder.examBuilder" />} title={test.title} description={test.description ?? <UiText message="builder.noDescription" />} />
      {builderState === "version-unavailable" ? <p role="status" className="notice mb-5"><UiText message="builder.versionUnavailable" /></p> : null}
      <section className="version-library surface-card overflow-hidden">
        <div className="section-header border-b border-[var(--line)] px-6 py-5">
          <div><h2 className="section-title"><UiText message="builder.versions" /></h2><p className="section-description"><UiText message="builder.versionsDescription" /></p></div>
        </div>
        <div className="divide-y divide-[var(--line)]">
          {test.versions.map((version) => (
            <Link key={version.id} href={builderEditPath(test.id, version.id)} className="version-row group">
              <div>
                <p className="font-semibold"><UiText message="common.versionNumber" params={{ number: version.version_number }} /> · <UiText message={version.status === "PUBLISHED" ? "builder.currentPublished" : version.status === "DRAFT" ? "common.draft" : "builder.historical"} /></p>
                <p className="mt-1 text-sm text-[var(--muted)]"><UiText message="builder.createdAt" params={{ date: formatProjectDateTime(version.created_at) }} /></p>
              </div>
              <div className="flex items-center gap-4"><StatusBadge status={version.status} label={<UiText message={version.status === "DRAFT" ? "common.draft" : version.status === "PUBLISHED" ? "common.published" : "common.archived"} />} /><ArrowIcon className="size-4 text-[var(--muted)] transition-transform group-hover:translate-x-1" /></div>
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}
