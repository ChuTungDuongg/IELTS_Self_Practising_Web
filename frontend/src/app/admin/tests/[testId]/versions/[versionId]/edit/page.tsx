import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { VersionActions } from "@/features/test-builder/version-actions";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { ReadingBuilder } from "@/features/test-builder/reading-builder";
import { getBuilderVersion } from "@/lib/api/builder";

export const dynamic = "force-dynamic";

export default async function VersionEditorPage({ params }: { params: Promise<{ testId: string; versionId: string }> }) {
  const { testId, versionId } = await params;
  const version = await getBuilderVersion(versionId).catch(() => null);
  if (!version || version.test_id !== testId) notFound();
  return (
    <>
      <PageHeading eyebrow="Exam builder" title={`${version.test_title} · Version ${version.version_number}`} action={<StatusBadge status={version.status} />} />
      <BuilderLifecycleProvider>
        <VersionActions testId={testId} versionId={versionId} status={version.status} />
        <section className="mt-8 grid gap-4 md:grid-cols-3">
          {(["READING", "LISTENING", "WRITING"] as const).map((kind) => {
            const moduleRecord = version.modules.find((item) => item.module_type === kind);
            return (
              <article key={kind} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5">
                <h2 className="font-semibold">{kind[0] + kind.slice(1).toLowerCase()}</h2>
                {moduleRecord ? (
                  <dl className="mt-4 space-y-2 text-sm text-[var(--muted)]">
                    <div className="flex justify-between"><dt>Passages</dt><dd>{moduleRecord.passages.length}</dd></div>
                    <div className="flex justify-between"><dt>Question groups</dt><dd>{moduleRecord.passages.reduce((sum, item) => sum + item.question_groups.length, 0)}</dd></div>
                  </dl>
                ) : <p className="mt-3 text-sm text-[var(--muted)]">Not created</p>}
              </article>
            );
          })}
        </section>
        {version.status === "DRAFT" ? <ReadingBuilder version={version} /> : <p className="mt-6 rounded-lg bg-[var(--surface-soft)] p-4 text-sm text-[var(--muted)]">This published version is frozen. Clone it to create an editable draft.</p>}
      </BuilderLifecycleProvider>
    </>
  );
}
