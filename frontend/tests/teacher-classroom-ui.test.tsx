import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { userSchema } from "@/lib/api/auth";
import { GlobalHeader } from "@/components/ui/global-header";
import { InvitationInbox } from "@/features/classrooms/invitation-inbox";
import { AssignmentList } from "@/features/classrooms/assignment-list";
import { TeacherTestList } from "@/features/classrooms/teacher-test-list";
import { ModerationActions } from "@/features/classrooms/moderation-actions";
import { TestAttribution } from "@/features/practice/library-content";
import { AdminUserActions } from "@/features/auth/admin-user-actions";
import { ApiError } from "@/lib/api/client";
import { renderWithLocale } from "./locale-test-utils";
const state = vi.hoisted(() => ({
  role: "TEACHER" as "USER" | "TEACHER" | "ADMIN",
  push: vi.fn(),
  refresh: vi.fn(),
  acceptInvitation: vi.fn(),
  declineInvitation: vi.fn(),
  startAssignment: vi.fn(),
  reviewModeration: vi.fn(),
  updateAdminUser: vi.fn()
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push, refresh: state.refresh }) }));
vi.mock("@/features/auth/auth-provider", () => ({
  useAuth: () => ({
    user: {
      id: "teacher",
      role: state.role,
      display_name: "Tutor"
    },
    loading: false,
    logout: vi.fn()
  })
}));
vi.mock("@/features/notifications/notification-center", () => ({ NotificationCenter: () => null }));
vi.mock("@/lib/api/classrooms", async (original) => ({
  ...await original<object>(),
  acceptInvitation: state.acceptInvitation,
  declineInvitation: state.declineInvitation,
  startAssignment: state.startAssignment
}));
vi.mock("@/lib/api/content-governance", async (original) => ({ ...await original<object>(), reviewModeration: state.reviewModeration }));
vi.mock("@/lib/api/admin", async (original) => ({ ...await original<object>(), updateAdminUser: state.updateAdminUser }));
beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  state.role = "TEACHER";
  state.acceptInvitation.mockResolvedValue({});
  state.declineInvitation.mockResolvedValue({});
  state.startAssignment.mockResolvedValue({ attempt_id: "attempt", test_session_id: null });
  state.reviewModeration.mockResolvedValue({});
});
it("accepts TEACHER auth and keeps teacher navigation out of ADMIN", () => {
  expect(userSchema.parse({
    id: "11111111-1111-4111-8111-111111111111",
    email: "t@example.com",
    display_name: "Tutor",
    role: "TEACHER",
    is_active: true,
    created_at: "now",
    updated_at: "now",
    last_login_at: null
  }).role).toBe("TEACHER");
  renderWithLocale(<GlobalHeader pathname="/teacher/tests" />);
  expect(screen.getByRole("link", { name: "Builder" })).toHaveAttribute("href", "/teacher/tests");
  expect(screen.getByRole("link", { name: "Classrooms" })).toHaveAttribute("href", "/teacher/classrooms");
  expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Transfer" })).not.toBeInTheDocument();
  expect(screen.getByText("Teacher")).toBeInTheDocument();
});
it("invitations require explicit Accept or Decline", async () => {
  renderWithLocale(<InvitationInbox invitations={[{
    id: "i",
    classroom_id: "c",
    classroom_name: "Evening",
    invited_email: "s@example.com",
    status: "PENDING",
    created_at: "now"
  }]} />);
  expect(state.acceptInvitation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  await waitFor(() => expect(state.acceptInvitation).toHaveBeenCalledWith("i"));
});
it("assignment starts use the assignment endpoint and navigate to the resulting attempt", async () => {
  renderWithLocale(<AssignmentList assignments={[{
    id: "a",
    classroom_id: "c",
    test_version_id: "v",
    created_by_user_id: "t",
    title: "Practice",
    note: null,
    status: "ACTIVE",
    created_at: "now",
    archived_at: null
  }]} />);
  fireEvent.click(screen.getByRole("button", { name: "Start assignment" }));
  expect(state.startAssignment).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue with this interface" }));
  await waitFor(() => expect(state.startAssignment).toHaveBeenCalledWith("a", {
    mode: "MODULE",
    module: "READING",
    scope: "FULL_MODULE",
    timer: { mode: "COUNT_UP" }
  }));
  expect(state.push).toHaveBeenCalledWith("/attempt/attempt");
});
it("owner-scoped tests only link to the teacher Builder", () => {
  const base = {
    title: "Owned",
    description: null,
    source_label: null,
    test_number: null,
    archived_at: null,
    created_at: "now",
    updated_at: "now",
    origin: "TEACHER" as const,
    owner_user_id: "teacher",
    versions: [{
      id: "v",
      version_number: 1,
      status: "DRAFT" as const,
      created_at: "now",
      published_at: null
    }]
  };
  renderWithLocale(<TeacherTestList tests={[{ ...base, id: "own" }, {
    ...base,
    id: "other",
    title: "Other private",
    owner_user_id: "someone-else"
  }]} ownerId="teacher" />);
  expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("href", "/teacher/tests/own/versions/v/edit");
  expect(screen.queryByText("Other private")).not.toBeInTheDocument();
});
it("moderation decisions are ADMIN controls only", async () => {
  const request = {
    id: "r",
    test_version_id: "v",
    scope: "CLASSROOM" as const,
    status: "PENDING" as const,
    submitted_by_user_id: "t",
    submitted_at: "now",
    submit_note: null,
    review_note: null,
    reviewed_at: null,
    reviewed_by_user_id: null,
    revoked_at: null,
    revoked_by_user_id: null,
    revoke_reason: null
  };
  const view = renderWithLocale(<ModerationActions request={request} />);
  expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  state.role = "ADMIN";
  view.rerender(<ModerationActions request={request} />);
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  await waitFor(() => expect(state.reviewModeration).toHaveBeenCalledWith("r", "approve", ""));
});
it("USER sees classrooms without authoring or administrator links", () => {
  state.role = "USER";
  renderWithLocale(<GlobalHeader pathname="/classrooms" />);
  expect(screen.getByRole("link", { name: "Classrooms" })).toHaveAttribute("href", "/classrooms");
  expect(screen.queryByRole("link", { name: "Builder" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
});
it("teacher labels localize without replacing navigation nodes", () => {
  renderWithLocale(<GlobalHeader pathname="/teacher/tests" />);
  const builder = screen.getByRole("link", { name: "Builder" });
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByRole("link", { name: "Biên soạn đề" })).toBe(builder);
  expect(screen.getByText("Giáo viên")).toBeInTheDocument();
});
it("ADMIN can promote and demote teachers while TEACHER has no role controls", async () => {
  const view = renderWithLocale(<AdminUserActions userId="student" role="USER" isActive />);
  expect(screen.queryByRole("button", { name: "Promote to teacher" })).not.toBeInTheDocument();
  state.role = "ADMIN";
  view.rerender(<AdminUserActions userId="student" role="USER" isActive />);
  fireEvent.click(screen.getByRole("button", { name: "Promote to teacher" }));
  await waitFor(() => expect(state.updateAdminUser).toHaveBeenCalledWith("student", { role: "TEACHER" }));
  view.rerender(<AdminUserActions userId="student" role="TEACHER" isActive />);
  fireEvent.click(screen.getByRole("button", { name: "Demote to user" }));
  await waitFor(() => expect(state.updateAdminUser).toHaveBeenCalledWith("student", { role: "USER" }));
});
it("Library distinguishes teacher attribution from Official content in EN and VI", () => {
  const base = {
    id: "test",
    title: "Fictional",
    description: null,
    source_label: null,
    test_number: null,
    archived_at: null,
    created_at: "now",
    updated_at: "now",
    versions: []
  };
  renderWithLocale(<>
    <TestAttribution test={{ ...base, origin: "ADMIN" }} />
    <TestAttribution test={{
      ...base,
      origin: "TEACHER",
      owner_display_name: "Tutor"
    }} />
  </>);
  expect(screen.getByText("Official")).toBeInTheDocument();
  expect(screen.getByText("Community · contributed by Tutor")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByText("Chính thức")).toBeInTheDocument();
  expect(screen.getByText("Cộng đồng · đóng góp bởi Tutor")).toBeInTheDocument();
});
it("single Writing Task 2 assignments default to Writing and retain the Task 2 focus label", async () => {
  const version = {
    id: "v",
    test_id: "test",
    test_title: "Writing only",
    version_number: 1,
    status: "PUBLISHED" as const,
    created_at: "now",
    published_at: "now",
    modules: [{
      id: "module",
      module_type: "WRITING" as const,
      title: null,
      recommended_duration_seconds: 1200,
      passage_count: 0,
      listening_part_count: 0,
      writing_task_count: 1,
      question_count: 0,
      writing_tasks: [{
        id: "task2",
        task_number: 2,
        task_type: null,
        prompt_excerpt: null,
        minimum_recommended_words: 250,
        recommended_duration_seconds: 1200
      }]
    }]
  };
  renderWithLocale(<AssignmentList assignments={[{
    id: "a",
    classroom_id: "c",
    test_version_id: "v",
    created_by_user_id: "t",
    version,
    title: null,
    note: null,
    status: "ACTIVE",
    created_at: "now",
    archived_at: null
  }]} />);
  expect(screen.getByRole("combobox", { name: "Practice mode" })).toHaveValue("WRITING");
  expect(screen.queryByRole("option", { name: "Full Mock" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Task 2" })).toHaveValue("task2");
  fireEvent.change(screen.getByRole("combobox", { name: "Skill practice" }), { target: { value: "task2" } });
  fireEvent.click(screen.getByRole("button", { name: "Start assignment" }));
  await waitFor(() => expect(state.startAssignment).toHaveBeenCalledWith("a", {
    mode: "MODULE",
    module: "WRITING",
    scope: "FOCUSED_UNIT",
    focused_unit: { kind: "WRITING_TASK", id: "task2" },
    timer: { mode: "COUNT_UP" }
  }));
});
it("teacher demotion conflicts explain required cleanup in EN and VI", async () => {
  state.role = "ADMIN";
  state.updateAdminUser.mockRejectedValueOnce(new ApiError("TEACHER_HAS_ACTIVE_RESOURCES", "English backend detail", 409));
  renderWithLocale(<AdminUserActions userId="teacher" role="TEACHER" isActive />);
  fireEvent.click(screen.getByRole("button", { name: "Demote to user" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Archive active classrooms");
  fireEvent.click(screen.getByText("Switch to Vietnamese"));
  expect(screen.getByRole("alert")).toHaveTextContent("Hãy lưu trữ các lớp đang hoạt động");
  expect(screen.queryByText("English backend detail")).not.toBeInTheDocument();
});
it("ADMIN result links use the shared authorized classroom route", () => {
  renderWithLocale(<AssignmentList resultNamespace="shared" canManage assignments={[{
    id: "a",
    classroom_id: "c",
    test_version_id: "v",
    created_by_user_id: "t",
    title: "Practice",
    note: null,
    status: "ACTIVE",
    created_at: "now",
    archived_at: null
  }]} />);
  expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute("href", "/classrooms/c/assignments/a/results");
});
