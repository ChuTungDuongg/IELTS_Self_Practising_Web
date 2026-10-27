import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { classroomPermissions } from "@/features/classrooms/classroom-permissions";
import { ClassroomManagement, ClassroomMembershipActions } from "@/features/classrooms/classroom-management";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ restoreClassroom: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: api.refresh }) }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), restoreClassroom: api.restoreClassroom }));
const room = { id: "room", teacher_id: "owner", name: "Fictional class", description: null, status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); api.restoreClassroom.mockResolvedValue({}); });

it("Admin read capabilities never become mutation permissions even with legacy capabilities", () => {
  const result = classroomPermissions({ ...room, capabilities: ["roster.view", "grades.view", "analytics.view", "classroom.manage", "members.manage", "staff.manage", "content.manage", "assignments.manage", "discussion.moderate", "grades.edit", "learning_plans.manage"] }, { id: "owner", role: "ADMIN" });
  expect(result).toMatchObject({ isObserver: true, isStudent: false, isStaff: false, canInspect: true, canViewRoster: true, canViewGrades: true, canViewAnalytics: true });
  for (const [name, allowed] of Object.entries(result)) if (name.startsWith("canManage") || name === "canEditGrades" || name === "canModerate" || name === "canScheduleAssignments") expect(allowed, name).toBe(false);
});

it("keeps co-teacher and TA actions scoped to returned capabilities", () => {
  expect(classroomPermissions({ ...room, classroom_role: "CO_TEACHER", capabilities: ["roster.view", "members.manage", "assignments.manage"] }, { id: "staff", role: "TEACHER" })).toMatchObject({ isStaff: true, canManageMembers: true, canManageAssignments: true, canManageClassroom: false, canEditGrades: false });
  expect(classroomPermissions({ ...room, capabilities: ["grades.view", "grades.edit"] }, { id: "ta", role: "USER" })).toMatchObject({ isStaff: true, isStudent: false, canViewGrades: true, canEditGrades: true, canManageAssignments: false, canViewRoster: false });
  expect(classroomPermissions({ ...room, capabilities: [] }, { id: "learner", role: "USER" })).toMatchObject({ isStudent: true, canViewGrades: false, canManageMembers: false });
});

it("renders an observer roster without forms, private email or membership actions", () => {
  renderWithLocale(<ClassroomManagement classroom={room} invitations={[]} members={[{ id: "membership", user_id: "learner", display_name: "Fictional learner", email: "learner@example.com", joined_at: "now", left_at: null, removed_by_user_id: null }]} observer canManageMembers canEditClassroom />);
  expect(screen.getByText("Fictional learner")).toBeInTheDocument();
  expect(screen.queryByText(/learner@example.com/)).not.toBeInTheDocument();
  expect(screen.queryAllByRole("button").filter(button => !button.textContent?.startsWith("Switch to"))).toHaveLength(0);
  expect(screen.queryByText("Invite student")).not.toBeInTheDocument();
  expect(document.querySelector("form")).toBeNull();
});

it("restores an archived classroom for its owner and renders no Admin lifecycle action", async () => {
  const archived = { ...room, status: "ARCHIVED" as const };
  const view = renderWithLocale(<ClassroomMembershipActions classroom={archived} isAdmin canManage isStaff />);
  expect(screen.queryAllByRole("button").filter(button => !button.textContent?.startsWith("Switch to"))).toHaveLength(0);
  view.unmount();
  renderWithLocale(<ClassroomMembershipActions classroom={archived} isAdmin={false} canManage isStaff />);
  fireEvent.click(screen.getByRole("button", { name: "Restore" }));
  await waitFor(() => expect(api.restoreClassroom).toHaveBeenCalledWith("room"));
});
