import Link from "next/link";
import { notFound } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { ModuleBadge } from "@/components/ui/module-badge";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFullMock } from "@/features/exam/start-full-mock";
import { getTest, getVersion } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

const moduleOrder = { READING: 0, LISTENING: 1, WRITING: 2 } as const;
const moduleLabel = { READING: "Reading", LISTENING: "Listening", WRITING: "Writing" } as const;

export default async function TestVersionLibraryPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = await params;
  const version = await getVersion(versionId).catch(() => null);
  if (!version || version.status !== "PUBLISHED") notFound();
  const test = await getTest(version.test_id).catch(() => null);
  if (!test) notFound();
  const modules = [...version.modules].sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);
  const missing = (["LISTENING", "READING", "WRITING"] as const).find((type) => !modules.some((item) => item.module_type === type));
  const missingDuration = modules.find((item) => !item.recommended_duration_seconds);
  const readinessWarnings = modules.filter((item) => (item.module_type === "READING" || item.module_type === "LISTENING") && item.question_count !== 40).map((item) => `${moduleLabel[item.module_type]} has ${item.question_count} questions. An official band will not be calculated.`);

  return <>
    <Link href="/library" className="practice-back-link">← Back to practice library</Link>
    <PageHeading eyebrow={`Published · Version ${version.version_number}`} title={test.title} description={test.description ?? "Choose a skill module and timer mode to begin."} />
    <StartFullMock versionId={version.id} warnings={readinessWarnings} unavailableReason={missing ? `${moduleLabel[missing]} module is missing.` : missingDuration ? `${moduleLabel[missingDuration.module_type]} recommended duration is missing.` : undefined} />
    <h2 className="mt-8 mb-4">Individual practice</h2><div className="practice-skill-grid">
      {modules.map((module) => <article key={module.id} className={`practice-card practice-card-${module.module_type.toLowerCase()}`}>
        <div className="practice-card-accent" aria-hidden="true" />
        <div className="practice-card-content">
          <div className="practice-card-topline"><ModuleBadge module={module.module_type} /></div>
          <div className="practice-card-title"><p className="practice-module-kicker">{moduleLabel[module.module_type]} practice</p><h2>{module.title ?? moduleLabel[module.module_type]}</h2><span>Continue with this skill in the published, frozen test version.</span></div>
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
