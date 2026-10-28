import { redirect } from "next/navigation";
import { listClassrooms, listMyInvitations, getClassroom, listAssignments, listMembers, listInvitations } from "@/lib/api/classrooms";
import { assignableTests } from "@/lib/api/classroom-lms";
import { MembersDashboard } from "./lms/members-dashboard";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { ClassroomDirectory } from "./classroom-directory";
import { ClassroomMembershipActions } from "./classroom-management";
import { AssignmentForm } from "./assignment-form";
import { ClassroomWorkspace, type ClassroomWorkspaceTab } from "./content/classroom-workspace";
import { classroomPermissions } from "./classroom-permissions";
export async function ClassroomsPage({ teacher = false }: {
  teacher?: boolean;
} = {}) {
  void teacher;
  const user = userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  if (user.role === "ADMIN") redirect("/admin/classrooms");
  const [items, invitations] = await Promise.all([listClassrooms(serverApiRequest), listMyInvitations(serverApiRequest)]);
  return <ClassroomDirectory items={items} invitations={invitations} user={{ id: user.id, role: user.role }} />;
}
export async function ClassroomDetailPage({ params, searchParams }: {
  params: Promise<{
    classroomId: string;
  }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { classroomId } = await params;
  const query = await searchParams;
  const postQuery = query?.post;
  const selectedAssignmentId = typeof query?.assignment === "string" ? query.assignment : null;
  const selectedPostId = typeof postQuery === "string" ? postQuery : null;
  const requestedTab = typeof query?.tab === "string" && ["stream", "classwork", "assignments", "calendar", "people", "gradebook", "analytics", "myProgress"].includes(query.tab) ? query.tab as ClassroomWorkspaceTab : undefined;
  const [classroom, user, assignments] = await Promise.all([getClassroom(classroomId, serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data)), listAssignments(classroomId, serverApiRequest)]);
  const permissions = classroomPermissions(classroom, user);
  const [members, invitations, tests] = await Promise.all([permissions.canViewRoster ? listMembers(classroomId, serverApiRequest) : [], permissions.canViewInvitations ? listInvitations(classroomId, serverApiRequest) : [], permissions.canManageAssignments ? assignableTests(classroomId, serverApiRequest) : []]);
  const hasManagement = permissions.canManageClassroom || permissions.canManageMembers || permissions.canManageStaff || permissions.isStudent && classroom.status === "ACTIVE";
  return <>
    <ClassroomWorkspace key={`${classroomId}-${user.id}-${user.role}-${selectedPostId ?? "feed"}-${selectedAssignmentId ?? ""}-${requestedTab ?? ""}`} classroom={classroom} user={{ id: user.id, role: user.role, display_name: user.display_name }} membersPreview={permissions.canViewRoster ? members.filter(member => !member.left_at).slice(0, 3).map(member => ({ user_id: member.user_id, display_name: member.display_name })) : undefined} assignments={assignments} selectedPostId={selectedPostId} selectedAssignmentId={selectedAssignmentId} initialTab={requestedTab}
      management={hasManagement ? <ClassroomMembershipActions key="membership-actions" classroom={classroom} canManage={permissions.canManageClassroom} isStaff={permissions.isStaff} isAdmin={permissions.isObserver} /> : undefined}
      people={permissions.canViewRoster ? <MembersDashboard key="classroom-people" classroom={classroom} members={members} invitations={invitations} assignmentCount={assignments.filter(item => item.status === "ACTIVE").length} canEditClassroom={permissions.canManageClassroom} canManageMembers={permissions.canManageMembers} canManageStaff={permissions.canManageStaff} canViewInvitations={permissions.canViewInvitations} observer={permissions.isObserver} /> : undefined}
      assignmentForm={permissions.canManageAssignments ? <AssignmentForm key="assignment-form" classroomId={classroomId} tests={tests} /> : undefined} />
  </>;
}
