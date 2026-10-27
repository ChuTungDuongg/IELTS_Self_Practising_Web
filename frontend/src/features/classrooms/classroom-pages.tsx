import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { listClassrooms, listMyInvitations, getClassroom, listAssignments, listMembers, listInvitations } from "@/lib/api/classrooms";
import { getTests } from "@/lib/api/tests";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";
import { UiText } from "@/lib/i18n/locale-provider";
import { InvitationInbox } from "./invitation-inbox";
import { ClassroomForm } from "./classroom-form";
import { ClassroomManagement, ClassroomMembershipActions } from "./classroom-management";
import { AssignmentForm } from "./assignment-form";
import { ClassroomWorkspace } from "./content/classroom-workspace";
import { ClassroomMetadata } from "./content/classroom-metadata";
export async function ClassroomsPage({ teacher = false }: {
  teacher?: boolean;
} = {}) {
  const [items, invitations, user] = await Promise.all([listClassrooms(serverApiRequest), listMyInvitations(serverApiRequest), serverApiRequest<unknown>("/auth/me").then(data => userSchema.parse(data))]);
  return <>
    <PageHeading title={<UiText message="classroom.title" />} />
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
  const canManage = user.role === "ADMIN" || (user.role === "TEACHER" && classroom.teacher_id === user.id);
  const [members, invitations, tests] = canManage ? await Promise.all([listMembers(classroomId, serverApiRequest), listInvitations(classroomId, serverApiRequest), getTests(undefined, serverApiRequest)]) : [[], [], []];
  return <>
    <PageHeading title={classroom.name} description={classroom.description} />
    <ClassroomMetadata classroom={classroom} />
    <ClassroomMembershipActions classroom={classroom} canManage={canManage} isAdmin={user.role === "ADMIN"} />
    <ClassroomWorkspace key={`${classroomId}-${user.id}-${user.role}-${selectedPostId ?? "feed"}-${selectedAssignmentId ?? ""}`} classroom={classroom} user={{ id: user.id, role: user.role }} assignments={assignments} canManage={canManage} selectedPostId={selectedPostId} selectedAssignmentId={selectedAssignmentId}
      people={canManage ? <ClassroomManagement classroom={classroom} members={members} invitations={invitations} /> : undefined}
      assignmentForm={canManage && classroom.status === "ACTIVE" ? <AssignmentForm classroomId={classroomId} tests={tests.filter(test => test.origin !== "TEACHER" || test.owner_user_id === classroom.teacher_id)} /> : undefined} />
  </>;
}
