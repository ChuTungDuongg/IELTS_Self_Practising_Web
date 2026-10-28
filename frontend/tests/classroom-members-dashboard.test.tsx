import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { MembersDashboard } from "@/features/classrooms/lms/members-dashboard";
import { renderWithLocale } from "./locale-test-utils";

const api = vi.hoisted(() => ({ getStaff: vi.fn(), removeMember: vi.fn(), inviteStudent: vi.fn(), inviteStaff: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: api.refresh }) }));
vi.mock("@/lib/api/classrooms", async original => ({ ...await original<object>(), removeMember: api.removeMember, inviteStudent: api.inviteStudent }));
vi.mock("@/lib/api/classroom-lms", async original => ({ ...await original<object>(), getStaff: api.getStaff, inviteStaff: api.inviteStaff }));
const room = { id: "room", teacher_id: "owner", teacher_name: "Owner", name: "Class", description: null, status: "ACTIVE" as const, archived_at: null, created_at: "now", updated_at: "now" };
const member = { id: "m", user_id: "student", display_name: "Nguyễn Anh", email: "student@example.com", joined_at: "now", left_at: null, removed_by_user_id: null };
const staff = { id: "s", classroom_id: "room", classroom_name: "Class", user_id: "staff", display_name: "Co Teacher", email: "staff@example.com", invited_by_user_id: "owner", staff_role: "CO_TEACHER" as const, status: "ACCEPTED" as const, content_manage: false, discussion_moderate: false, analytics_view: false, learning_plans_manage: false, created_at: "now", accepted_at: "now", revoked_at: null };
const props = { classroom: room, members: [member], invitations: [], assignmentCount: 3, canEditClassroom: false, canManageMembers: true, canManageStaff: true, canViewInvitations: true, observer: false };
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value() { this.setAttribute("open", ""); } }); Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value() { this.removeAttribute("open"); this.dispatchEvent(new Event("close")); } }); api.getStaff.mockResolvedValue([staff, { ...staff, id: "pending", user_id: "pending", display_name: "Pending Teacher", status: "PENDING" }, { ...staff, id: "revoked", user_id: "revoked", status: "REVOKED" }]); api.removeMember.mockResolvedValue(undefined); api.inviteStudent.mockResolvedValue({}); api.inviteStaff.mockResolvedValue({}); });

it("groups accepted members, filters search and confirms student removal", async () => {
  renderWithLocale(<MembersDashboard {...props} />);
  expect(await screen.findByText("Co Teacher")).toBeInTheDocument();
  expect(screen.getByText("Nguyễn Anh")).toBeInTheDocument();
  expect(screen.getByText("Pending Teacher")).toBeInTheDocument();
  expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "Students" }));
  expect(screen.queryByText("Co Teacher")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "All" }));
  fireEvent.change(screen.getByLabelText("Search members by name, email or role"), { target: { value: "nguyễn" } });
  expect(screen.getByText("Nguyễn Anh")).toBeInTheDocument(); expect(screen.queryByText("Co Teacher")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Remove student" }));
  expect(api.removeMember).not.toHaveBeenCalled();
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove student" }));
  await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith("room", "student"));
});

it("keeps an observer read-only and does not expose emails in search or rows", async () => {
  renderWithLocale(<MembersDashboard {...props} observer />);
  expect(await screen.findByText("Co Teacher")).toBeInTheDocument();
  expect(screen.queryByText(/student@example.com|staff@example.com/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Invite member" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove student" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search members by name, email or role"), { target: { value: "student@example.com" } });
  expect(screen.queryByText("Nguyễn Anh")).not.toBeInTheDocument();
});

it("invites staff with the selected permissions", async () => {
  renderWithLocale(<MembersDashboard {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Invite member" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Invitation type"), { target: { value: "TEACHING_ASSISTANT" } });
  fireEvent.change(within(dialog).getByLabelText("Account email"), { target: { value: "assistant@example.com" } });
  fireEvent.click(within(dialog).getByLabelText("View analytics"));
  fireEvent.click(within(dialog).getByRole("button", { name: "Invite member" }));
  await waitFor(() => expect(api.inviteStaff).toHaveBeenCalledWith("room", expect.objectContaining({ staff_role: "TEACHING_ASSISTANT", email: "assistant@example.com", analytics_view: true, content_manage: false })));
});

it("invites a student through the shared dialog", async () => {
  renderWithLocale(<MembersDashboard {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Invite member" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Account email"), { target: { value: "learner@example.com" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Invite member" }));
  await waitFor(() => expect(api.inviteStudent).toHaveBeenCalledWith("room", "learner@example.com"));
});
