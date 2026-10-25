import { UiText } from "@/lib/i18n/locale-provider";
import { PageHeading } from "@/components/ui/page-heading";
import { DataLoadNotice } from "@/components/ui/data-load-notice";
import { SkillPractice } from "@/features/practice/skill-practice";
import { getTests, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import type { VersionDetail } from "@/lib/api/schema";

export const dynamic = "force-dynamic";

export default async function PracticePage({ searchParams }: { searchParams?: Promise<{ skill?: string | string[] }> } = {}) {
  const requestedSkill = (await searchParams)?.skill;
  const initialSkill = typeof requestedSkill === "string" && ["READING", "LISTENING", "WRITING", "SPEAKING"].includes(requestedSkill.toUpperCase()) ? requestedSkill.toUpperCase() as "READING" | "LISTENING" | "WRITING" | "SPEAKING" : "READING";
  const tests = await getTests({ publicOnly: true }, serverApiRequest);
  const published = tests.filter((test) => !test.archived_at).flatMap((test) => {
    const version = [...test.versions].reverse().find((item) => item.status === "PUBLISHED");
    return version ? [version] : [];
  });
  const details = await Promise.all(published.map((version) => getVersion(version.id, serverApiRequest, { publicOnly: true }).catch(() => null)));
  const available = details.filter((detail): detail is VersionDetail => detail !== null && detail.status === "PUBLISHED");
  const loadFailed = details.some(detail => detail === null);

  return <>
    <PageHeading eyebrow={<UiText message="pages.practice" />} title={<UiText message="pages.skillPractice" />} description={<UiText message="pages.skillPracticeDescription" />} />
    {loadFailed ? <DataLoadNotice /> : null}
    {available.length || !loadFailed ? <SkillPractice key={initialSkill} versions={available} initialSkill={initialSkill} /> : null}
  </>;
}
