import { PageHeading } from "@/components/ui/page-heading";
import { TransferPortal, type TransferTestOption } from "@/features/transfer/transfer-portal";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function TransferPage() {
  const [active, archived] = await Promise.all([
    getTests(undefined, serverApiRequest),
    getTests({ archived: true }, serverApiRequest),
  ]);
  const summaries = [...active, ...archived];
  const tests: TransferTestOption[] = await Promise.all(summaries.map(async (test) => {
    const latest = [...test.versions].sort((left, right) => right.version_number - left.version_number)[0];
    const detail = latest ? await getVersion(latest.id, serverApiRequest).catch(() => null) : null;
    return {
      id: test.id,
      title: test.title,
      latestVersion: latest?.version_number ?? null,
      states: [...new Set(test.versions.map((version) => version.status))],
      skills: detail?.modules.map((module) => module.module_type) ?? [],
      archived: test.archived_at !== null,
    };
  }));
  return <><PageHeading eyebrow="Local portability" title="Test transfer" description="Export authored tests with their images and audio, then import them into another installation." /><TransferPortal tests={tests} /></>;
}
