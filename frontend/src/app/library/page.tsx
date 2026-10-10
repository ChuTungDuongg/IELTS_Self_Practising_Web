import { LibraryContent } from "@/features/practice/library-content";
import type { VersionDetail } from "@/lib/api/schema";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function LibraryPage() {
  const tests = await getTests(undefined, serverApiRequest).catch(() => []);
  const published = tests.flatMap((test) => {
    const version = [...test.versions].reverse().find((item) => item.status === "PUBLISHED");
    return version ? [{ test, version }] : [];
  });
  const available = (await Promise.all(published.map(async (item) => ({
    ...item,
    detail: await getVersion(item.version.id, serverApiRequest).catch(() => null),
  })))).filter((item): item is typeof item & { detail: VersionDetail } => item.detail !== null);

  return <LibraryContent items={available} />;
}
