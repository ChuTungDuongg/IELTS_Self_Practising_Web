export const BUILDER_EDIT_ROUTE = "/admin/tests/[testId]/versions/[versionId]/edit";

export function builderEditPath(testId: string, versionId: string): string {
  return `/admin/tests/${encodeURIComponent(testId)}/versions/${encodeURIComponent(versionId)}/edit`;
}
