import { UiText } from "@/lib/i18n/locale-provider";
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
  return <><PageHeading eyebrow={<UiText message="transfer.portability" />} title={<UiText message="transfer.title" />} description={<UiText message="transfer.description" />} /><TransferPortal tests={tests} /></>;
}
