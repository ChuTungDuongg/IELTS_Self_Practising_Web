import { LibraryVersionContent } from "@/features/practice/library-content";
import { notFound } from "next/navigation";
import { getTest, getVersion } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";


export default async function TestVersionLibraryPage({ params }: { params: Promise<{ versionId: string }> }) {
  const { versionId } = await params;
  const version = await getVersion(versionId, serverApiRequest).catch(() => null);
  if (!version || version.status !== "PUBLISHED") notFound();
  const test = await getTest(version.test_id, serverApiRequest).catch(() => null);
  if (!test) notFound();
  return <LibraryVersionContent test={test} version={version} />;
}
