import { notFound } from "next/navigation";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import { getBuilderVersion } from "@/lib/api/builder";
import { serverApiRequest } from "@/lib/api/server-client";
export const dynamic = "force-dynamic";
export default async function TeacherPreviewPage({ params, searchParams }: {
  params: Promise<{
    testId: string;
    versionId: string;
  }>;
  searchParams: Promise<{
    module?: string;
  }>;
}) {
  const { testId, versionId } = await params;
  const requested = (await searchParams).module;
  const moduleType = requested === "listening" ? "LISTENING" : requested === "reading" ? "READING" : requested === "writing" ? "WRITING" : null;
  const version = await getBuilderVersion(versionId, serverApiRequest);
  if (version.test_id !== testId || !moduleType)
    notFound();
  return <DraftPreview version={version} moduleType={moduleType} namespace="teacher" />;
}
