import type { Classroom } from "@/lib/api/classrooms";

/** FastAPI remains authoritative; Admin never implies classroom membership. */
export function classroomPermissions(classroom: Classroom, user: { id: string; role: string }) {
  const isObserver = user.role === "ADMIN";
  const owner = user.role === "TEACHER" && user.id === classroom.teacher_id;
  const has = (capability: string) => classroom.capabilities?.includes(capability) ?? owner;
  const active = classroom.status === "ACTIVE";
  const write = (capability: string) => !isObserver && active && has(capability);
  const isStaff = !isObserver && (owner || ["CO_TEACHER", "TEACHING_ASSISTANT"].includes(classroom.classroom_role ?? "") || !!classroom.capabilities?.length);
  return {
    isObserver, isStaff, isStudent: !isObserver && !isStaff,
    canInspect: isObserver || isStaff,
    canViewRoster: has("roster.view"), canViewGrades: has("grades.view"), canViewAnalytics: has("analytics.view"),
    canViewInvitations: !isObserver && has("members.manage"),
    canManageClassroom: !isObserver && has("classroom.manage"),
    canManageMembers: write("members.manage"), canManageStaff: write("staff.manage"),
    canManageContent: write("content.manage"), canManageAssignments: write("assignments.manage"),
    canScheduleAssignments: !isObserver && has("assignments.manage"),
    canEditGrades: write("grades.edit"), canModerate: write("discussion.moderate"), canManagePlans: write("learning_plans.manage"),
  };
}
