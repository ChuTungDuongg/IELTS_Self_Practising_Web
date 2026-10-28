"use client";
import type { TestSummary } from "@/lib/api/schema";
import { AuthoringLibrary } from "@/features/test-builder/test-library-list";
export function TeacherTestList({ tests, archivedTests = [], ownerId, loadError = false }: { tests: TestSummary[]; archivedTests?: TestSummary[]; ownerId: string; loadError?: boolean }) {
  const owned = (items: TestSummary[]) => items.filter(test => test.owner_user_id === ownerId && test.origin === "TEACHER");
  return <AuthoringLibrary namespace="teacher" activeTests={owned(tests)} archivedTests={owned(archivedTests)} loadError={loadError} />;
}
