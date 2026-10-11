export const BUILDER_EDIT_ROUTE = "/admin/tests/[testId]/versions/[versionId]/edit";
export const TRANSFER_ROUTE = "/transfer";

export type BuilderNamespace = "admin" | "teacher";
export function builderEditPath(testId: string, versionId: string, namespace: BuilderNamespace = "admin"): string {
  return `/${namespace}/tests/${encodeURIComponent(testId)}/versions/${encodeURIComponent(versionId)}/edit`;
}

export function builderPreviewPath(testId: string, versionId: string, module: "reading" | "listening" | "writing", namespace: BuilderNamespace = "admin"): string {
  return `/${namespace}/tests/${encodeURIComponent(testId)}/versions/${encodeURIComponent(versionId)}/preview?module=${module}`;
}
