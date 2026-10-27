import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { listClassrooms, listMyInvitations, getClassroom, listAssignments, listMembers, listInvitations } from "@/lib/api/classrooms";
import { assignableTests } from "@/lib/api/classroom-lms";
import { StaffManagement, StaffInvitationInbox } from "./lms/staff-management";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { InvitationInbox } from "./invitation-inbox";
import { ClassroomForm } from "./classroom-form";
import { ClassroomManagement, ClassroomMembershipActions } from "./classroom-management";
import { AssignmentForm } from "./assignment-form";
import { ClassroomWorkspace } from "./content/classroom-workspace";
export async function ClassroomsPage({ teacher = false }: {
  teacher?: boolean;
} = {}) {
  const [items, invitations, user] = await Promise.all([listClassrooms(serverApiRequest), listMyInvitations(serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data))]);
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
  const owner = user.role === "TEACHER" && classroom.teacher_id === user.id;
  const canManage = classroom.capabilities?.includes("grades.view") ?? (user.role === "ADMIN" || owner);
  const canMembers = classroom.capabilities?.includes("members.manage") ?? canManage;
  const canAssign = classroom.capabilities?.includes("assignments.manage") ?? canManage;
  const [members, invitations, tests] = await Promise.all([canMembers ? listMembers(classroomId, serverApiRequest) : [], canMembers ? listInvitations(classroomId, serverApiRequest) : [], canAssign || user.role === "ADMIN" ? assignableTests(classroomId, serverApiRequest) : []]);
  return <>
    <ClassroomWorkspace key={`${classroomId}-${user.id}-${user.role}-${selectedPostId ?? "feed"}-${selectedAssignmentId ?? ""}`} classroom={classroom} user={{ id: user.id, role: user.role }} assignments={assignments} canManage={canManage} selectedPostId={selectedPostId} selectedAssignmentId={selectedAssignmentId}
      management={<ClassroomMembershipActions key="membership-actions" classroom={classroom} canManage={classroom.capabilities?.includes("classroom.manage") ?? canManage} isStaff={canManage} isAdmin={user.role === "ADMIN"} />}
      people={canManage ? <div key="classroom-people">{canMembers ? <ClassroomManagement classroom={classroom} members={members} invitations={invitations} /> : null}<StaffManagement classroomId={classroomId} canManage={owner} archived={classroom.status === "ARCHIVED"} /></div> : undefined}
      assignmentForm={(canAssign || user.role === "ADMIN") && classroom.status === "ACTIVE" ? <AssignmentForm key="assignment-form" classroomId={classroomId} tests={tests} /> : undefined} />
  </>;
}
