import { ClassroomOverviewPage } from "@/features/classrooms/overview/classroom-overview-page";

export const dynamic = "force-dynamic";
export default function Page({ params }: { params: Promise<{ classroomId: string }> }) {
  return <ClassroomOverviewPage params={params} />;
}
