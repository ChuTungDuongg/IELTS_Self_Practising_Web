import Link from "next/link";
import { PlusIcon } from "@/components/ui/icons";
import { PageHeading } from "@/components/ui/page-heading";
import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { getTests } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function AdminTestsPage() {
  const [activeTests, archivedTests] = await Promise.all([
    getTests(undefined, serverApiRequest).catch(() => []),
    getTests({ archived: true }, serverApiRequest).catch(() => []),
  ]);
  return (
    <>
      <PageHeading
        eyebrow="Authoring workspace"
        eyebrowClassName="authoring-eyebrow"
        title="Test Library"
        description="Create, manage, and publish structured IELTS tests. Published versions stay frozen so every attempt remains historically accurate."
        action={<Link href="/admin/tests/new" className="btn btn-primary"><PlusIcon className="size-4" /> New test</Link>}
      />
      <TestLibraryList activeTests={activeTests} archivedTests={archivedTests} />
    </>
  );
}
