import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminUserList } from "@/features/auth/admin-user-list";
import { deleteAdminUser, updateAdminUser } from "@/lib/api/admin";
import type { AdminStats, AdminUserList as AdminUserListData } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
vi.mock("@/lib/api/admin", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/admin")>(),
  updateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
}));

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "ada@example.com",
  display_name: "Ada Student",
  role: "USER" as const,
  is_active: false,
  created_at: "2026-09-20T00:00:00Z",
  last_login_at: null,
  attempt_count: 2,
  last_activity_at: null,
};
const stats: AdminStats = {
  total_users: 5, active_users: 3, users_with_attempts: 2, total_attempts: 4,
  active_attempts: 1, completed_attempts: 3, completed_full_mocks: 0,
  attempts_by_skill: { LISTENING: 0, READING: 4, WRITING: 0 },
};
const inactiveUsers: AdminUserListData = { items: [user], total: 1, offset: 0, limit: 50 };

describe("AdminUserList", () => {
  beforeEach(() => vi.clearAllMocks());

  it("navigates between server-filtered statuses while preserving the search term", () => {
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="Ada" stats={stats} />);

    expect(screen.getByRole("tab", { name: "Deactivated Users (2)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Ada Student" })).toHaveAttribute("href", `/admin/users/${user.id}`);
    const form = screen.getByRole("search");
    expect(form).toHaveAttribute("action", "/admin");
    expect(within(form).getByDisplayValue("deactivated")).toHaveAttribute("name", "status");
    expect(screen.getByPlaceholderText("Search email or name")).toHaveValue("Ada");

    fireEvent.click(screen.getByRole("tab", { name: "Active Users (3)" }));
    expect(push).toHaveBeenCalledWith("/admin?status=active&search=Ada");
  });

  it("navigates through filtered user pages", () => {
    const paged = { ...inactiveUsers, total: 31, limit: 25 };
    const view = render(<AdminUserList users={paged} status="deactivated" search="Ada" stats={stats} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(push).toHaveBeenCalledWith("/admin?status=deactivated&search=Ada&offset=25");

    view.rerender(<AdminUserList users={{ ...paged, offset: 25 }} status="deactivated" search="Ada" stats={stats} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(push).toHaveBeenCalledWith("/admin?status=deactivated&search=Ada");
  });

  it("deactivates from the active list and updates both counts immediately", async () => {
    vi.mocked(updateAdminUser).mockResolvedValue({ ...user, is_active: false, updated_at: "2026-09-20T00:00:00Z" });
    render(<AdminUserList users={{ ...inactiveUsers, items: [{ ...user, is_active: true }] }} status="active" search="" stats={stats} />);

    expect(screen.queryByRole("button", { name: /Delete permanently/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ada Student" }));

    await waitFor(() => expect(screen.queryByRole("link", { name: "Ada Student" })).not.toBeInTheDocument());
    expect(updateAdminUser).toHaveBeenCalledWith(user.id, { is_active: false });
    expect(screen.getByRole("tab", { name: "Active Users (2)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Deactivated Users (3)" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Deactivated Ada Student");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("reactivates from the deactivated list and updates both counts immediately", async () => {
    vi.mocked(updateAdminUser).mockResolvedValue({ ...user, is_active: true, updated_at: "2026-09-20T00:00:00Z" });
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);

    fireEvent.click(screen.getByRole("button", { name: "Reactivate Ada Student" }));

    await waitFor(() => expect(screen.queryByRole("link", { name: "Ada Student" })).not.toBeInTheDocument());
    expect(updateAdminUser).toHaveBeenCalledWith(user.id, { is_active: true });
    expect(screen.getByRole("tab", { name: "Active Users (4)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Deactivated Users (1)" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Reactivated Ada Student");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("deletes permanently only after confirmation and updates counts", async () => {
    vi.mocked(deleteAdminUser).mockResolvedValue();
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Ada Student" }));
    expect(deleteAdminUser).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("personal learning data, including 2 attempts and their history");
    expect(screen.getByRole("dialog")).toHaveTextContent("cannot be undone");
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));

    await waitFor(() => expect(screen.queryByRole("link", { name: "Ada Student" })).not.toBeInTheDocument());
    expect(deleteAdminUser).toHaveBeenCalledWith(user.id);
    expect(screen.getByRole("tab", { name: "Deactivated Users (1)" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Permanently deleted Ada Student");
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("cancels permanent deletion without changing the user", () => {
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Ada Student" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(deleteAdminUser).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Ada Student" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks deactivated rows visibly", () => {
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);

    expect(screen.getByRole("link", { name: "Ada Student" }).closest(".admin-user-row"))
      .toHaveClass("admin-user-row-inactive");
    expect(screen.getByText("DEACTIVATED")).toHaveClass("status-badge");
  });

  it("keeps the user and shows the backend error if permanent deletion fails", async () => {
    vi.mocked(deleteAdminUser).mockRejectedValue(new ApiError("USER_DELETE_BLOCKED", "User cannot be deleted yet.", 409));
    render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);

    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Ada Student" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("User cannot be deleted yet.");
    expect(screen.getByRole("link", { name: "Ada Student" })).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("reconciles rows and counts from refreshed server data", async () => {
    vi.mocked(deleteAdminUser).mockResolvedValue();
    const view = render(<AdminUserList users={inactiveUsers} status="deactivated" search="" stats={stats} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Ada Student" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());

    const serverUser = { ...user, id: "22222222-2222-4222-8222-222222222222", display_name: "New Student" };
    view.rerender(<AdminUserList users={{ ...inactiveUsers, items: [serverUser], total: 1 }} status="deactivated" search="" stats={{ ...stats, total_users: 5 }} />);

    expect(await screen.findByRole("link", { name: "New Student" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Deactivated Users (2)" })).toBeInTheDocument();
  });

  it("keeps a path to earlier users after deleting the last row on a later page", async () => {
    vi.mocked(deleteAdminUser).mockResolvedValue();
    render(<AdminUserList users={{ ...inactiveUsers, total: 26, offset: 25, limit: 25 }} status="deactivated" search="" stats={stats} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently Ada Student" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());

    expect(screen.getByRole("heading", { name: "No users on this page" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(push).toHaveBeenCalledWith("/admin?status=deactivated");
  });
});
