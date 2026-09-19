import { notFound } from "next/navigation";
import { DraftPreview } from "@/features/test-builder/draft-preview";
import { getBuilderVersion } from "@/lib/api/builder";

export const dynamic = "force-dynamic";

export default async function PreviewPage({ params, searchParams }: { params: Promise<{ testId: string; versionId: string }>; searchParams: Promise<{ module?: string }> }) {
  const { testId, versionId } = await params;
  const requested = (await searchParams).module;
  const moduleType = requested === "listening" ? "LISTENING" : requested === "reading" ? "READING" : null;
  const version = await getBuilderVersion(versionId).catch(() => null);
  if (!version || version.test_id !== testId || version.status !== "DRAFT" || !moduleType) notFound();
  return <DraftPreview version={version} moduleType={moduleType} />;
}
