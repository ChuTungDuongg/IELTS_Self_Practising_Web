import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { getTests, getVersion } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

const moduleOrder = { READING: 0, LISTENING: 1, WRITING: 2 } as const;

export default async function LibraryPage() {
  const tests = await getTests().catch(() => []);
  const published = tests.flatMap((test) => {
    const version = [...test.versions].reverse().find((item) => item.status === "PUBLISHED");
    return version ? [{ test, version }] : [];
  });
  const available = (await Promise.all(published.map(async (item) => ({
    ...item,
    detail: await getVersion(item.version.id).catch(() => null),
  })))).filter((item) => item.detail);

  return <>
    <PageHeading eyebrow="Practice" title="Choose your next test" description="Open one frozen test version, then choose the Reading, Listening, or Writing module you want to practise." />
    {available.length ? <div className="practice-grid">
      {available.map(({ test, version, detail }) => {
        const modules = [...detail!.modules].sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);
        return <article key={version.id} className="practice-card practice-test-card">
          <div className="practice-card-accent" aria-hidden="true" />
          <div className="practice-card-content">
            <div className="practice-card-topline"><span className="practice-version">Version {version.version_number}</span><StatusBadge status={version.status} /></div>
            <div className="practice-card-title"><p className="practice-module-kicker">Complete test</p><h2>{test.title}</h2><span>{test.description ?? "A published IELTS practice test."}</span></div>
            <div className="practice-module-chips" aria-label={`${test.title} skills`}>{modules.map((module) => <ModuleBadge key={module.id} module={module.module_type} />)}</div>
            <p className="practice-skill-count">{modules.length} skills available</p>
            <Link className="btn btn-primary practice-open-test" href={`/library/${version.id}`}>Open test <ArrowIcon className="size-4" /></Link>
          </div>
        </article>;
      })}
    </div> : <EmptyState title="No published tests yet" description="Publish a valid version in the Builder and it will appear here, ready for practice." />}
  </>;
}
