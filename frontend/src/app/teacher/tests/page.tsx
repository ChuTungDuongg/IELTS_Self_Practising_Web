import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { getTests } from "@/lib/api/tests";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { TeacherTestList } from "@/features/classrooms/teacher-test-list";
export const dynamic = "force-dynamic";
export default async function TeacherTestsPage() {
  const [tests, user] = await Promise.all([getTests(undefined, serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data))]);
  return <>
    <PageHeading title={<UiText message="teacher.tests" />} description={<UiText message="moderation.requireReview" />} action={<Link href="/teacher/tests/new" className="btn btn-primary">
      <UiText message="builder.createDraft" />
    </Link>} />
    <TeacherTestList tests={tests} ownerId={user.id} />
  </>;
}
