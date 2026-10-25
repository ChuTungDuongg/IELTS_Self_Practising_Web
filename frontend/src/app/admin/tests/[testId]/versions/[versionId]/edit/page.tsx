import { BuilderEditorPage } from "@/features/test-builder/builder-editor-page";
export const dynamic = "force-dynamic";
export default async function AdminVersionEditorPage(props: {
  params: Promise<{ testId: string; versionId: string }>;
  searchParams?: Promise<{ workspace?: string | string[] }>;
}) {
  return BuilderEditorPage(props);
}
