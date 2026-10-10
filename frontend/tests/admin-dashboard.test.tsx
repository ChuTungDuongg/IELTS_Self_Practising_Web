import { fireEvent, render, screen } from "@testing-library/react";
import { renderWithLocale } from "./locale-test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminDashboardPage from "@/app/admin/page";
import { getAdminStats, getAdminUsers } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";
import { AdminGuard } from "@/features/auth/admin-guard";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin", useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/api/admin", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/api/admin")>(),
  getAdminStats: vi.fn(),
  getAdminUsers: vi.fn(),
}));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { role: "USER" }, loading: false, sessionError: null }) }));

const stats = {
  total_users: 5, active_users: 3, users_with_attempts: 2, total_attempts: 4,
  active_attempts: 1, completed_attempts: 3, completed_full_mocks: 0,
  attempts_by_skill: { LISTENING: 0, READING: 4, WRITING: 0 },
};

describe("AdminDashboardPage", () => {
  it("localizes the existing forbidden guard without exposing protected content", () => {
    window.localStorage.clear();
    renderWithLocale(<AdminGuard><p>Protected content</p></AdminGuard>);
    expect(screen.getByRole("heading", { name: "Forbidden" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Không có quyền truy cập" })).toBeInTheDocument();
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
  });
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(getAdminStats).mockResolvedValue(stats);
    vi.mocked(getAdminUsers).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 });
  });

  it("localizes dashboard and search without refetching or replacing the search draft", async () => {
    renderWithLocale(await AdminDashboardPage({ searchParams: Promise.resolve({ status: "deactivated", search: "Ada" }) }));
    const input = screen.getByPlaceholderText("Search email or name");
    fireEvent.change(input, { target: { value: "Ada <raw>" } });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("heading", { name: "Bảng điều khiển nền tảng" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Tìm email hoặc tên")).toBe(input);
    expect(input).toHaveValue("Ada <raw>");
    expect(screen.getByRole("tab", { name: "Người dùng đã vô hiệu hóa (2)" })).toHaveAttribute("aria-selected", "true");
    expect(getAdminStats).toHaveBeenCalledOnce();
    expect(getAdminUsers).toHaveBeenCalledOnce();
  });

  it("requests only deactivated users with the search term", async () => {
    render(await AdminDashboardPage({ searchParams: Promise.resolve({ status: "deactivated", search: "  Ada  " }) }));

    expect(getAdminUsers).toHaveBeenCalledExactlyOnceWith({ isActive: false, search: "Ada", offset: 0 }, serverApiRequest);
    expect(screen.getByRole("tab", { name: "Deactivated Users (2)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("search")).toContainElement(screen.getByPlaceholderText("Search email or name"));
  });

  it("defaults to server-filtered active users", async () => {
    render(await AdminDashboardPage({ searchParams: Promise.resolve({}) }));

    expect(getAdminUsers).toHaveBeenCalledExactlyOnceWith({ isActive: true, search: "", offset: 0 }, serverApiRequest);
    expect(screen.getByRole("tab", { name: "Active Users (3)" })).toHaveAttribute("aria-selected", "true");
  });

  it("passes a valid page offset to the filtered API", async () => {
    render(await AdminDashboardPage({ searchParams: Promise.resolve({ status: "deactivated", offset: "25" }) }));
    expect(getAdminUsers).toHaveBeenCalledExactlyOnceWith({ isActive: false, search: "", offset: 25 }, serverApiRequest);
  });

  it("replaces list state when the server navigates to a different status", async () => {
    const activeUser = {
      id: "11111111-1111-4111-8111-111111111111", email: "active@example.com", display_name: "Active Student",
      role: "USER" as const, is_active: true, created_at: "2026-09-20T00:00:00Z",
      last_login_at: null, attempt_count: 0, last_activity_at: null,
    };
    const inactiveUser = { ...activeUser, id: "22222222-2222-4222-8222-222222222222", email: "inactive@example.com", display_name: "Inactive Student", is_active: false };
    vi.mocked(getAdminUsers)
      .mockResolvedValueOnce({ items: [activeUser], total: 1, offset: 0, limit: 50 })
      .mockResolvedValueOnce({ items: [inactiveUser], total: 1, offset: 0, limit: 50 });
    const view = render(await AdminDashboardPage({ searchParams: Promise.resolve({ status: "active" }) }));
    expect(screen.getByRole("link", { name: "Active Student" })).toBeInTheDocument();

    view.rerender(await AdminDashboardPage({ searchParams: Promise.resolve({ status: "deactivated" }) }));

    expect(screen.queryByRole("link", { name: "Active Student" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inactive Student" })).toBeInTheDocument();
  });
});
