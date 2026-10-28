import { getTests } from "@/lib/api/tests";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { TeacherTestList } from "@/features/classrooms/teacher-test-list";
export const dynamic = "force-dynamic";
export default async function TeacherTestsPage() {
  const [active, archived, user] = await Promise.all([getTests(undefined, serverApiRequest).then(value => ({ value, failed: false })).catch(() => ({ value: [], failed: true })), getTests({ archived: true }, serverApiRequest).then(value => ({ value, failed: false })).catch(() => ({ value: [], failed: true })), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data))]);
  return <TeacherTestList tests={active.value} archivedTests={archived.value} ownerId={user.id} loadError={active.failed || archived.failed} />;
}
