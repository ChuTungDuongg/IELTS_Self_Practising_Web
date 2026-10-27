import { LibraryContent } from "@/features/practice/library-content";
import type { VersionDetail } from "@/lib/api/schema";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import { selectedPublishedVersion } from "@/lib/published-version";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const tests = await getTests({ publicOnly: true }, serverApiRequest);
  const published = tests.flatMap((test) => {
    const version = selectedPublishedVersion(test.versions);
    return version ? [{ test, version }] : [];
  });
  const available = (await Promise.all(published.map(async (item) => ({
    ...item,
    detail: await getVersion(item.version.id, serverApiRequest, { publicOnly: true }).catch(() => null),
  })))).filter((item): item is typeof item & { detail: VersionDetail } => item.detail !== null);

  return <LibraryContent items={available} loadFailed={available.length !== published.length} />;
}
