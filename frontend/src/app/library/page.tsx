import { LibraryContent } from "@/features/practice/library-content";
import type { VersionDetail } from "@/lib/api/schema";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import { selectedPublishedVersion } from "@/lib/published-version";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const tests = await getTests({ publicOnly: true, includeDetails: true }, serverApiRequest).catch(() => null);
  if (!tests) return <LibraryContent items={[]} loadFailed />;

  const published = tests.filter(test => !test.archived_at).flatMap(test => {
    const version = selectedPublishedVersion(test.versions);
    return version ? [{ test, version }] : [];
  });
  const results = await Promise.all(published.map(async item => {
    const detail = item.test.published_detail?.id === item.version.id
      ? item.test.published_detail
      : await getVersion(item.version.id, serverApiRequest, { publicOnly: true }).catch(() => null);
    return { ...item, detail: detail?.id === item.version.id && detail.test_id === item.test.id && detail.status === "PUBLISHED" ? detail : null };
  }));
  const available = results.filter((item): item is typeof item & { detail: VersionDetail } => item.detail !== null);
  return <LibraryContent items={available} loadFailed={available.length !== published.length} />;
}
