import { ClassroomsPage } from "@/features/classrooms/classroom-pages";
export const dynamic = "force-dynamic";
export default async function TeacherClassroomsPage() {
  return ClassroomsPage({ teacher: true });
}
