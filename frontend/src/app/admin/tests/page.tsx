import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { getTests } from "@/lib/api/tests";

export const dynamic = "force-dynamic";

export default async function AdminTestsPage() {
  const [activeTests, archivedTests] = await Promise.all([
    getTests().catch(() => []),
    getTests({ archived: true }).catch(() => []),
  ]);
  return (
    <>
      <PageHeading
        eyebrow="Exam builder"
        title="Tests"
        description="Create logical tests, then publish immutable versions when their module content is valid."
        action={<Link href="/admin/tests/new" className="rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--accent-strong)]">New test</Link>}
      />
      <TestLibraryList activeTests={activeTests} archivedTests={archivedTests} />
    </>
  );
}
