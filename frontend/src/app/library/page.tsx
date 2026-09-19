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
  const published = tests.flatMap((test) =>
    test.versions
      .filter((version) => version.status === "PUBLISHED")
      .map((version) => ({ test, version })),
  );
  const available = (await Promise.all(published.map(async (item) => ({ ...item, detail: await getVersion(item.version.id).catch(() => null) })))).filter((item) => item.detail);
  return (
    <>
      <PageHeading eyebrow="Practice" title="Choose your next test" description="Published, frozen test versions available for a focused Reading practice session." />
      {available.length ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {available.flatMap(({ test, version, detail }) => detail!.modules.filter((module) => module.module_type === "READING" || module.module_type === "LISTENING").map((module) => (
            <article key={`${version.id}-${module.module_type}`} className="surface-card group overflow-hidden">
              <div className={`h-1 bg-gradient-to-r ${module.module_type === "LISTENING" ? "from-violet-700 to-fuchsia-400" : "from-sky-600 to-cyan-400"}`} />
              <div className="p-6">
              <div className="flex items-start justify-between gap-3">
                <ModuleBadge module={module.module_type} />
                <StatusBadge status={version.status} />
              </div>
              <h2 className="mt-5 text-xl font-semibold tracking-tight">{test.title}</h2>
              <p className="mt-2 min-h-12 text-sm leading-6 text-[var(--muted)]">{test.description ?? `A published ${module.module_type === "LISTENING" ? "Listening" : "Reading"} practice test.`}</p>
              <Link className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-[var(--accent)]" href={`/admin/tests/${test.id}`}>
                View version {version.version_number} <ArrowIcon className="size-4 transition-transform group-hover:translate-x-1" />
              </Link>
              <StartAttempt versionId={version.id} module={module.module_type as "READING" | "LISTENING"} />
              </div>
            </article>
          ))) }
        </div>
      ) : (
        <EmptyState title="No published tests yet" description="Publish a valid version in the Builder and it will appear here, ready for practice." />
      )}
    </>
  );
}
