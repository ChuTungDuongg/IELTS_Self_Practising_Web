import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { VersionActions } from "@/features/test-builder/version-actions";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { ReadingBuilder } from "@/features/test-builder/reading-builder";
import { ListeningBuilder } from "@/features/test-builder/listening-builder";
import { getBuilderVersion } from "@/lib/api/builder";
import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { ModuleBadge } from "@/components/ui/module-badge";
import { ApiError } from "@/lib/api/client";

export const dynamic = "force-dynamic";

export default async function VersionEditorPage({ params }: { params: Promise<{ testId: string; versionId: string }> }) {
  const { testId, versionId } = await params;
  let version;
  try {
    version = await getBuilderVersion(versionId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  if (version.test_id !== testId) notFound();
  return (
    <>
      <PageHeading eyebrow="IELTS Studio · Engine Builder" title={version.test_title} description={`Version ${version.version_number} · Structured authoring workspace`} action={<StatusBadge status={version.status} />} />
      <BuilderLifecycleProvider>
        <VersionActions testId={testId} versionId={versionId} status={version.status} />
        <div className="builder-workspace">
          <aside className="builder-local-nav" aria-label="Builder sections">
            <p>Test structure</p>
            <a href="#overview"><BuilderIcon className="size-4" /> Overview</a>
            <a href="#reading" className="builder-local-active"><ReadingIcon className="size-4" /> Reading</a>
            <a href="#listening"><span className="module-listening-dot" /> Listening</a>
            <span><span className="module-writing-dot" /> Writing <small>Not created</small></span>
          </aside>
          <div className="builder-canvas">
            <section id="overview" className="builder-overview">
              <div className="section-header"><div><h2 className="section-title">Test overview</h2><p className="section-description">A quick view of the modules currently included in this version.</p></div></div>
              <div className="module-overview-grid">
                {(["READING", "LISTENING", "WRITING"] as const).map((kind) => {
                  const moduleRecord = version.modules.find((item) => item.module_type === kind);
                  const groups = (moduleRecord?.passages.reduce((sum, item) => sum + item.question_groups.length, 0) ?? 0) + (moduleRecord?.listening_parts.reduce((sum, item) => sum + item.question_groups.length, 0) ?? 0);
                  return (
                    <article key={kind} className={`module-overview-card module-card-${kind.toLowerCase()}`}>
                      <div className="flex items-center justify-between gap-3"><ModuleBadge module={kind} /><span className="module-state">{moduleRecord ? "Active" : "Not created"}</span></div>
                      <dl><div><dt>{kind === "READING" ? "Passages" : "Sections"}</dt><dd>{kind === "LISTENING" ? moduleRecord?.listening_parts.length ?? 0 : moduleRecord?.passages.length ?? 0}</dd></div><div><dt>Groups</dt><dd>{groups}</dd></div></dl>
                    </article>
                  );
                })}
              </div>
            </section>
            <div id="reading">
              {version.status === "DRAFT" ? <ReadingBuilder version={version} /> : <p className="notice mt-6">This published version is frozen. Clone it to create an editable draft.</p>}
            </div>
            {version.status === "DRAFT" ? <ListeningBuilder version={version} /> : null}
          </div>
        </div>
      </BuilderLifecycleProvider>
    </>
  );
}
