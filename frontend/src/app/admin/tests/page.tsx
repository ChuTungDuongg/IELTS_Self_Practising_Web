import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { getTests } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
export const dynamic = "force-dynamic";
export default async function AdminTestsPage() {
  const [active, archived] = await Promise.allSettled([getTests(undefined, serverApiRequest), getTests({ archived: true }, serverApiRequest)]);
  return <TestLibraryList activeTests={active.status === "fulfilled" ? active.value : []} archivedTests={archived.status === "fulfilled" ? archived.value : []} loadError={active.status === "rejected" || archived.status === "rejected"} />;
}
