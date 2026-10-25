import { ClassroomResultsPage } from "@/features/classrooms/classroom-result-pages";
export const dynamic = "force-dynamic";
export default async function TeacherResultsPage(props: {
  params: Promise<{ classroomId: string; assignmentId: string }>;
  searchParams?: Promise<{ offset?: string }>;
}) {
  return ClassroomResultsPage(props);
}
