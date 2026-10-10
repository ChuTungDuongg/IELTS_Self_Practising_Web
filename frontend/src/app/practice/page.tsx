import { UiText } from "@/lib/i18n/locale-provider";
import { PageHeading } from "@/components/ui/page-heading";
import { SkillPractice } from "@/features/practice/skill-practice";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import type { VersionDetail } from "@/lib/api/schema";

export const dynamic = "force-dynamic";

export default async function PracticePage() {
  const tests = await getTests(undefined, serverApiRequest).catch(() => []);
  const published = tests.filter((test) => !test.archived_at).flatMap((test) => {
    const version = [...test.versions].reverse().find((item) => item.status === "PUBLISHED");
    return version ? [version] : [];
  });
  const details = await Promise.all(published.map((version) => getVersion(version.id, serverApiRequest).catch(() => null)));
  const available = details.filter((detail): detail is VersionDetail => detail !== null && detail.status === "PUBLISHED");

  return <>
    <PageHeading eyebrow={<UiText message="pages.practice" />} title={<UiText message="pages.skillPractice" />} description={<UiText message="pages.skillPracticeDescription" />} />
    <SkillPractice versions={available} />
  </>;
}
