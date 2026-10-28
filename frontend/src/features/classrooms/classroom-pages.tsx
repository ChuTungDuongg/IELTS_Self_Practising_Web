import Link from "next/link";
import { redirect } from "next/navigation";
import { PageHeading } from "@/components/ui/page-heading";
import { listClassrooms, listMyInvitations, getClassroom, listAssignments, listMembers, listInvitations } from "@/lib/api/classrooms";
import { assignableTests } from "@/lib/api/classroom-lms";
import { StaffInvitationInbox } from "./lms/staff-management";
import { MembersDashboard } from "./lms/members-dashboard";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { InvitationInbox } from "./invitation-inbox";
import { ClassroomForm } from "./classroom-form";
import { ClassroomMembershipActions } from "./classroom-management";
import { AssignmentForm } from "./assignment-form";
import { ClassroomWorkspace } from "./content/classroom-workspace";
import { classroomPermissions } from "./classroom-permissions";
export async function ClassroomsPage({ teacher = false }: {
  teacher?: boolean;
} = {}) {
  const user = userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  if (user.role === "ADMIN") redirect("/admin/classrooms");
  const [items, invitations] = await Promise.all([listClassrooms(serverApiRequest), listMyInvitations(serverApiRequest)]);
  return <>
    <PageHeading title={<UiText message="classroom.title" />} />
    <StaffInvitationInbox />
    <InvitationInbox invitations={invitations} />{teacher ? <ClassroomForm /> : null}{items.length ? <div className="test-card-grid">{items.map(item => <article key={item.id} className="surface-card p-5">
      <h2>{item.name}</h2>
      <p>{item.description}</p>
      <p>
        <UiText message={item.status === "ARCHIVED" ? "classroom.archived" : "classroom.active"} />
      </p>
      <Link className="btn btn-secondary mt-3" href={`${teacher && item.teacher_id === user.id ? "/teacher/classrooms" : "/classrooms"}/${item.id}`}>
        <UiText message="common.open" />
      </Link>
    </article>)}</div> : <p>
      <UiText message="classroom.empty" />
    </p>}</>;
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
  const [classroom, user, assignments] = await Promise.all([getClassroom(classroomId, serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data)), listAssignments(classroomId, serverApiRequest)]);
  const permissions = classroomPermissions(classroom, user);
  const [members, invitations, tests] = await Promise.all([permissions.canViewRoster ? listMembers(classroomId, serverApiRequest) : [], permissions.canViewInvitations ? listInvitations(classroomId, serverApiRequest) : [], permissions.canManageAssignments ? assignableTests(classroomId, serverApiRequest) : []]);
  const hasManagement = permissions.canManageClassroom || permissions.canManageMembers || permissions.canManageStaff || permissions.isStudent && classroom.status === "ACTIVE";
  return <>
    <ClassroomWorkspace key={`${classroomId}-${user.id}-${user.role}-${selectedPostId ?? "feed"}-${selectedAssignmentId ?? ""}`} classroom={classroom} user={{ id: user.id, role: user.role, display_name: user.display_name }} membersPreview={permissions.canViewRoster ? members.filter(member => !member.left_at).slice(0, 3).map(member => ({ user_id: member.user_id, display_name: member.display_name })) : undefined} assignments={assignments} selectedPostId={selectedPostId} selectedAssignmentId={selectedAssignmentId} initialTab={query?.tab === "people" && permissions.canViewRoster ? "people" : undefined}
      management={hasManagement ? <ClassroomMembershipActions key="membership-actions" classroom={classroom} canManage={permissions.canManageClassroom} isStaff={permissions.isStaff} isAdmin={permissions.isObserver} /> : undefined}
      people={permissions.canViewRoster ? <MembersDashboard key="classroom-people" classroom={classroom} members={members} invitations={invitations} assignmentCount={assignments.filter(item => item.status === "ACTIVE").length} canEditClassroom={permissions.canManageClassroom} canManageMembers={permissions.canManageMembers} canManageStaff={permissions.canManageStaff} canViewInvitations={permissions.canViewInvitations} observer={permissions.isObserver} /> : undefined}
      assignmentForm={permissions.canManageAssignments ? <AssignmentForm key="assignment-form" classroomId={classroomId} tests={tests} /> : undefined} />
  </>;
}
