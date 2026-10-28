import { userSchema } from "@/lib/api/auth";
import { getClassroom, listAssignments, listMemberPreview } from "@/lib/api/classrooms";
import { listFeed } from "@/lib/api/classroom-content";
import { dashboardSchema } from "@/lib/api/classroom-learning";
import { getAssignmentCalendar } from "@/lib/api/assignment-scheduling";
import { serverApiRequest } from "@/lib/api/server-client";
import { classroomPermissions } from "../classroom-permissions";
import { ClassroomOverview } from "./classroom-overview";

export async function ClassroomOverviewPage({ params, teacher = false }: { params: Promise<{ classroomId: string }>; teacher?: boolean }) {
  const { classroomId } = await params;
  // Resolve authorization first; no dashboard data is requested before the detail check.
  const [classroom, user] = await Promise.all([getClassroom(classroomId, serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data))]);
  const permissions = classroomPermissions(classroom, user);
  const now = new Date(), end = new Date(now.valueOf() + 90 * 86400000);
  const [assignments, feed, calendar, dashboard, members] = await Promise.allSettled([
    listAssignments(classroomId, serverApiRequest),
    listFeed(classroomId, { status: "PUBLISHED" }, serverApiRequest),
    getAssignmentCalendar(classroomId, now.toISOString(), end.toISOString(), 0, undefined, serverApiRequest),
    permissions.canViewAnalytics ? serverApiRequest<unknown>(`/classrooms/${encodeURIComponent(classroomId)}/analytics`).then(data => dashboardSchema.parse(data)) : Promise.resolve(null),
    permissions.canViewRoster ? listMemberPreview(classroomId, serverApiRequest) : Promise.resolve(null),
  ]);
  const directory = permissions.isObserver ? "/admin/classrooms" : teacher ? "/teacher/classrooms" : "/classrooms";
  const workspace = `${teacher ? "/teacher/classrooms" : "/classrooms"}/${classroomId}`;
  return <ClassroomOverview classroom={classroom} permissions={permissions} directory={directory} workspace={workspace}
    assignments={assignments.status === "fulfilled" ? assignments.value : null}
    posts={feed.status === "fulfilled" ? feed.value.items.filter(post => post.status === "PUBLISHED").slice(0, 3) : null}
    calendar={calendar.status === "fulfilled" ? calendar.value : null}
    dashboard={dashboard.status === "fulfilled" ? dashboard.value : null}
    members={members.status === "fulfilled" ? members.value?.map(({ user_id, display_name }) => ({ user_id, display_name })) ?? null : null} />;
}
