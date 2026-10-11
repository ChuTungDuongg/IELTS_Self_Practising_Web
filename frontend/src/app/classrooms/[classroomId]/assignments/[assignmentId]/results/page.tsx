import { ClassroomResultsPage } from "@/features/classrooms/classroom-result-pages";
export const dynamic = "force-dynamic";
export default async function ResultsPage({ params, searchParams }: {
  params: Promise<{
    classroomId: string;
    assignmentId: string;
  }>;
  searchParams?: Promise<{ offset?: string; }>;
}) {
  return ClassroomResultsPage({ params, searchParams, namespace: "shared" });
}
