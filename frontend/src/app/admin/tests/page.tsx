import { UiText } from "@/lib/i18n/locale-provider";
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
        eyebrow={<UiText message="builder.workspace" />}
        eyebrowClassName="authoring-eyebrow"
        title={<UiText message="builder.library" />}
        description={<UiText message="builder.libraryDescription" />}
        action={<Link href="/admin/tests/new" className="btn btn-primary"><PlusIcon className="size-4" /> <UiText message="builder.newTest" /></Link>}
      />
      <TestLibraryList activeTests={activeTests} archivedTests={archivedTests} />
    </>
  );
}
