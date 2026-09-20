import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { getTests, getVersion } from "@/lib/api/tests";
import { StartAttempt } from "@/features/exam/start-attempt";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const tests = await getTests().catch(() => []);
  const published = tests.flatMap((test) => {
    const version = [...test.versions].reverse().find((item) => item.status === "PUBLISHED");
    return version ? [{ test, version }] : [];
  });
  const available = (await Promise.all(published.map(async (item) => ({ ...item, detail: await getVersion(item.version.id).catch(() => null) })))).filter((item) => item.detail);
  return (
    <>
      <PageHeading eyebrow="Practice" title="Choose your next test" description="Published, frozen test versions available for focused Reading, Listening, and Writing practice sessions." />
      {available.length ? (
        <div className="practice-grid">
          {available.flatMap(({ test, version, detail }) => detail!.modules.map((module) => (
            <article key={`${version.id}-${module.module_type}`} className={`practice-card practice-card-${module.module_type.toLowerCase()}`}>
              <div className="practice-card-accent" aria-hidden="true" />
              <div className="practice-card-content">
                <div className="practice-card-topline">
                  <ModuleBadge module={module.module_type} />
                  <StatusBadge status={version.status} />
                </div>
                <div className="practice-card-title">
                  <p>{module.module_type === "LISTENING" ? "Listening practice" : module.module_type === "WRITING" ? "Writing practice" : "Reading practice"}</p>
                  <h2>{test.title}</h2>
                  <span>{test.description ?? `A published ${module.module_type === "LISTENING" ? "Listening" : module.module_type === "WRITING" ? "Writing" : "Reading"} practice test.`}</span>
                </div>
                <dl className="practice-card-meta">
                  <div><dt>Version</dt><dd>{version.version_number}</dd></div>
                  <div><dt>{module.module_type === "WRITING" ? "Tasks" : "Questions"}</dt><dd>{module.module_type === "WRITING" ? module.writing_task_count : module.question_count}</dd></div>
                  <div><dt>{module.module_type === "LISTENING" ? "Sections" : module.module_type === "WRITING" ? "Suggested time" : "Passages"}</dt><dd>{module.module_type === "LISTENING" ? module.listening_part_count : module.module_type === "WRITING" ? `${Math.round((module.recommended_duration_seconds ?? 3600) / 60)} min` : module.passage_count}</dd></div>
                </dl>
                <Link className="practice-version-link" href={`/admin/tests/${test.id}`}>
                  View published version <ArrowIcon className="size-4" />
                </Link>
                <StartAttempt versionId={version.id} module={module.module_type} />
              </div>
            </article>
          )))}
        </div>
      ) : (
        <EmptyState title="No published tests yet" description="Publish a valid version in the Builder and it will appear here, ready for practice." />
      )}
    </>
  );
}
