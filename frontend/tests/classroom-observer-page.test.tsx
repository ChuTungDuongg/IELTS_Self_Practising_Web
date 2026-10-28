import type { ReactNode } from "react";
import { screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ClassroomDetailPage, ClassroomsPage } from "@/features/classrooms/classroom-pages";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ user: vi.fn(), getClassroom: vi.fn(), listAssignments: vi.fn(), listMembers: vi.fn(), listInvitations: vi.fn(), assignableTests: vi.fn(), listClassrooms: vi.fn(), listMyInvitations: vi.fn(), redirect: vi.fn(), workspace: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: api.user }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), getClassroom: api.getClassroom, listAssignments: api.listAssignments, listMembers: api.listMembers, listInvitations: api.listInvitations, listClassrooms: api.listClassrooms, listMyInvitations: api.listMyInvitations }));
vi.mock("@/lib/api/classroom-lms", async original => ({ ...await original<object>(), assignableTests: api.assignableTests }));
vi.mock("next/navigation", () => ({ redirect: api.redirect, useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/features/classrooms/lms/staff-management", () => ({ StaffManagement: () => <p>Staff roster</p>, StaffInvitationInbox: () => null }));
vi.mock("@/features/classrooms/content/classroom-workspace", () => ({ ClassroomWorkspace: (props: { people?: ReactNode; management?: ReactNode; assignmentForm?: ReactNode }) => { api.workspace(props); return <>{props.people}{props.management}{props.assignmentForm}</>; } }));
const ownerId = "11111111-1111-4111-8111-111111111111";
const room = { id: "22222222-2222-4222-8222-222222222222", teacher_id: ownerId, name: "Fictional classroom", status: "ACTIVE", capabilities: ["roster.view", "grades.view", "analytics.view"] };
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  api.user.mockResolvedValue({ id: "33333333-3333-4333-8333-333333333333", role: "ADMIN", display_name: "Observer", email: "admin@example.com", is_active: true, created_at: "now", updated_at: "now", last_login_at: null });
  api.getClassroom.mockResolvedValue(room); api.listAssignments.mockResolvedValue([]); api.listMembers.mockResolvedValue([]); api.listInvitations.mockResolvedValue([]); api.assignableTests.mockResolvedValue([]);
});

it("fetches only roster reads for Admin and preserves roster and assignment deep links", async () => {
  renderWithLocale(await ClassroomDetailPage({ params: Promise.resolve({ classroomId: room.id }), searchParams: Promise.resolve({ tab: "people", assignment: "homework" }) }));
  expect(api.listMembers).toHaveBeenCalledWith(room.id, api.user);
  expect(api.listInvitations).not.toHaveBeenCalled(); expect(api.assignableTests).not.toHaveBeenCalled();
  expect(api.workspace).toHaveBeenCalledWith(expect.objectContaining({ initialTab: "people", selectedAssignmentId: "homework", management: undefined, assignmentForm: undefined }));
  expect(screen.getByRole("heading", { name: "Class members" })).toBeInTheDocument();
  expect(screen.queryByText("Invite student")).not.toBeInTheDocument();
});

it("routes Admin classroom browsing to the paginated directory before listing every room", async () => {
  api.redirect.mockImplementation(() => { throw new Error("directory redirect"); });
  await expect(ClassroomsPage()).rejects.toThrow("directory redirect");
  expect(api.redirect).toHaveBeenCalledWith("/admin/classrooms");
  expect(api.listClassrooms).not.toHaveBeenCalled(); expect(api.listMyInvitations).not.toHaveBeenCalled();
});
