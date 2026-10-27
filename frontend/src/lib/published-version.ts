/** Choose only among the caller's already-authorized versions. Never widens access. */
export function selectedPublishedVersion<T extends { id: string; status: string; version_number: number }>(versions: T[]): T | undefined {
  return versions.filter(version => version.status === "PUBLISHED").sort((left, right) => right.version_number - left.version_number || left.id.localeCompare(right.id))[0];
}
