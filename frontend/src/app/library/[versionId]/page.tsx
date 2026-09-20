import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { ModuleBadge } from "@/components/ui/module-badge";
import { StartAttempt } from "@/features/exam/start-attempt";
import { getTest, getVersion } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

const moduleOrder = { READING: 0, LISTENING: 1, WRITING: 2 } as const;

export default async function TestVersionLibraryPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = await params;
  const version = await getVersion(versionId).catch(() => null);
  if (!version || version.status !== "PUBLISHED") notFound();
  const test = await getTest(version.test_id).catch(() => null);
  if (!test) notFound();
  const modules = [...version.modules].sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);

  return <>
    <Link href="/library" className="practice-back-link">← Back to practice library</Link>
    <PageHeading eyebrow={`Published · Version ${version.version_number}`} title={test.title} description={test.description ?? "Choose a skill module and timer mode to begin."} />
    <div className="practice-skill-grid">
      {modules.map((module) => <article key={module.id} className={`practice-card practice-card-${module.module_type.toLowerCase()}`}>
        <div className="practice-card-accent" aria-hidden="true" />
        <div className="practice-card-content">
          <div className="practice-card-topline"><ModuleBadge module={module.module_type} /></div>
          <div className="practice-card-title"><p>{module.module_type} practice</p><h2>{module.title ?? module.module_type.charAt(0) + module.module_type.slice(1).toLowerCase()}</h2><span>Continue with this skill in the published, frozen test version.</span></div>
          <dl className="practice-card-meta">
            <div><dt>Version</dt><dd>{version.version_number}</dd></div>
            <div><dt>{module.module_type === "WRITING" ? "Tasks" : "Questions"}</dt><dd>{module.module_type === "WRITING" ? module.writing_task_count : module.question_count}</dd></div>
            <div><dt>{module.module_type === "LISTENING" ? "Sections" : module.module_type === "WRITING" ? "Suggested time" : "Passages"}</dt><dd>{module.module_type === "LISTENING" ? module.listening_part_count : module.module_type === "WRITING" ? `${Math.round((module.recommended_duration_seconds ?? 3600) / 60)} min` : module.passage_count}</dd></div>
          </dl>
          <StartAttempt versionId={version.id} module={module.module_type} />
        </div>
      </article>)}
    </div>
  </>;
}
