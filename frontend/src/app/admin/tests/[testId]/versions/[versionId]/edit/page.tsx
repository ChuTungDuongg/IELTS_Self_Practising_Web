import { UiText } from "@/lib/i18n/locale-provider";
import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { VersionActions } from "@/features/test-builder/version-actions";
import { BuilderLifecycleProvider } from "@/features/test-builder/builder-lifecycle";
import { ReadingBuilder } from "@/features/test-builder/reading-builder";
import { ListeningBuilder } from "@/features/test-builder/listening-builder";
import { WritingBuilder } from "@/features/test-builder/writing-builder";
import { BuilderWorkspaceNavigation, type BuilderWorkspace } from "@/features/test-builder/builder-workspace-navigation";
import { TestDetailsHeading } from "@/features/test-builder/test-details-heading";
import { ContentSummary, builderContentSummary } from "@/features/test-builder/content-summary";
import { getBuilderVersion } from "@/lib/api/builder";
import { ModuleBadge } from "@/components/ui/module-badge";
import { ApiError } from "@/lib/api/client";
import { getTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function VersionEditorPage({ params, searchParams }: { params: Promise<{ testId: string; versionId: string }>; searchParams?: Promise<{ workspace?: string | string[] }> }) {
  const { testId, versionId } = await params;
  const requestedWorkspace = (await searchParams)?.workspace;
  const workspace: BuilderWorkspace = typeof requestedWorkspace === "string" && ["overview", "reading", "listening", "writing"].includes(requestedWorkspace) ? requestedWorkspace as BuilderWorkspace : "overview";
  let version;
  try {
    version = await getBuilderVersion(versionId, serverApiRequest);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      const test = await getTest(testId, serverApiRequest).catch(() => null);
      if (!test) redirect("/admin/tests");
      const currentDraft = [...test.versions]
        .filter((item) => item.status === "DRAFT")
        .sort((left, right) => right.version_number - left.version_number)[0];
      if (currentDraft && currentDraft.id !== versionId) redirect(builderEditPath(test.id, currentDraft.id));
      redirect(`/admin/tests/${encodeURIComponent(test.id)}?builder=version-unavailable`);
    }
    throw error;
  }
  if (version.test_id !== testId) notFound();
  return (
    <>
      {version.status === "DRAFT" ? <TestDetailsHeading testId={testId} initialTitle={version.test_title} initialDescription={version.test_description ?? null} versionNumber={version.version_number} /> : <PageHeading eyebrow={<UiText message="builder.brand" />} title={version.test_title} description={<UiText message="builder.versionWorkspace" params={{ number: version.version_number }} />} action={<StatusBadge status={version.status} label={<UiText message={version.status === "PUBLISHED" ? "common.published" : "common.archived"} />} />} />}
      <BuilderLifecycleProvider>
        <VersionActions testId={testId} version={version} />
        <div className="builder-workspace">
          <BuilderWorkspaceNavigation testId={testId} versionId={versionId} workspace={workspace} moduleTypes={version.modules.map((item) => item.module_type)} />
          <div className="builder-canvas">
            {workspace === "overview" ? <section className="builder-overview">
              <div className="section-header"><div><h2 className="section-title"><UiText message="builder.overview" /></h2><p className="section-description"><UiText message="builder.overviewDescription" /></p></div></div>
              <div className="module-overview-grid">
                {(["READING", "LISTENING", "WRITING"] as const).map((kind) => {
                  const moduleRecord = version.modules.find((item) => item.module_type === kind);
                  const groups = (moduleRecord?.passages.reduce((sum, item) => sum + item.question_groups.length, 0) ?? 0) + (moduleRecord?.listening_parts.reduce((sum, item) => sum + item.question_groups.length, 0) ?? 0);
                  return (
                    <article key={kind} className={`module-overview-card module-card-${kind.toLowerCase()}`}>
                      <div className="flex items-center justify-between gap-3"><ModuleBadge module={kind} label={<UiText message={kind === "READING" ? "common.reading" : kind === "LISTENING" ? "common.listening" : "common.writing"} />} /><span className="module-state"><UiText message={moduleRecord ? "builder.active" : "builder.notCreated"} /></span></div>
                      <dl><div><dt><UiText message={kind === "READING" ? "common.passages" : kind === "LISTENING" ? "common.sections" : "common.tasks"} /></dt><dd>{kind === "LISTENING" ? moduleRecord?.listening_parts.length ?? 0 : kind === "WRITING" ? moduleRecord?.writing_tasks.length ?? 0 : moduleRecord?.passages.length ?? 0}</dd></div><div><dt><UiText message={kind === "WRITING" ? "builder.promptsReady" : "builder.groups"} /></dt><dd>{kind === "WRITING" ? moduleRecord?.writing_tasks.filter((task) => task.prompt.trim()).length ?? 0 : groups}</dd></div></dl>
                      {moduleRecord ? <p className="section-description"><UiText message="builder.recommendedTime" /> {moduleRecord.recommended_duration_seconds ? <UiText message="common.minutesShort" params={{ count: moduleRecord.recommended_duration_seconds / 60 }} /> : <UiText message="builder.notSet" />}{version.status === "DRAFT" ? <> · <Link href={`${builderEditPath(testId, versionId)}?workspace=${kind.toLowerCase()}`}><UiText message="builder.editDuration" /></Link></> : null}</p> : null}
                      <ContentSummary units={builderContentSummary(moduleRecord)} />
                    </article>
                  );
                })}
              </div>
            </section> : null}
            {workspace === "reading" ? <div>
              {version.status === "DRAFT" ? <ReadingBuilder version={version} /> : <p className="notice mt-6"><UiText message="builder.frozen" /></p>}
            </div> : null}
            {workspace === "listening" ? version.status === "DRAFT" ? <ListeningBuilder version={version} /> : <p className="notice mt-6"><UiText message="builder.frozen" /></p> : null}
            {workspace === "writing" ? version.status === "DRAFT" ? <WritingBuilder version={version} /> : <p className="notice mt-6"><UiText message="builder.frozen" /></p> : null}
          </div>
        </div>
      </BuilderLifecycleProvider>
    </>
  );
}
