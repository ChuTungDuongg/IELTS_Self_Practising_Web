import { ClassroomOverviewPage } from "@/features/classrooms/overview/classroom-overview-page";

export const dynamic = "force-dynamic";
export default function TeacherClassroomOverviewPage(props: { params: Promise<{ classroomId: string }> }) {
  return <ClassroomOverviewPage {...props} teacher />;
}
