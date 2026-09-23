import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/page";
import { getAdminStats } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { serverApiRequest } from "@/lib/api/server-client";
import { getHistory } from "@/lib/api/history";
import { getTests } from "@/lib/api/tests";

vi.mock("@/lib/api/admin", () => ({ getAdminStats: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/lib/api/history", () => ({ getHistory: vi.fn() }));
vi.mock("@/lib/api/tests", () => ({ getTests: vi.fn() }));
vi.mock("@/features/auth/admin-only", () => ({ AdminOnly: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/home/interactive-planet", () => ({ InteractivePlanet: () => null }));

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@example.com",
  display_name: "Admin",
  role: "ADMIN",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_login_at: null,
};

describe("homepage Admin Users metric", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getTests).mockResolvedValue([]);
    vi.mocked(getHistory).mockResolvedValue({ items: [], groups: [], sessions: [], total: 0 });
    vi.mocked(serverApiRequest).mockResolvedValue(user);
    vi.mocked(getAdminStats).mockResolvedValue({ total_users: 14, active_users: 12 } as never);
  });

  it("shows the ADMIN-only count, active subcount, and admin destination", async () => {
    render(await DashboardPage());
    const metric = screen.getByRole("link", { name: /14\s*Users\s*12 active/i });
    expect(metric).toHaveAttribute("href", "/admin");
    expect(getAdminStats).toHaveBeenCalledWith(serverApiRequest);
  });

  it("does not request or show platform stats for a USER", async () => {
    vi.mocked(serverApiRequest).mockResolvedValue({ ...user, role: "USER" });
    render(await DashboardPage());
    expect(getAdminStats).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: /Users/ })).not.toBeInTheDocument();
  });

  it("does not request platform stats for an unauthenticated visitor", async () => {
    vi.mocked(serverApiRequest).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    render(await DashboardPage());
    expect(getAdminStats).not.toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: /Users/ })).not.toBeInTheDocument();
  });

  it("surfaces session backend errors instead of treating them as a USER", async () => {
    vi.mocked(serverApiRequest).mockRejectedValue(new ApiError("API_ERROR", "Backend failed", 500));
    await expect(DashboardPage()).rejects.toThrow("Backend failed");
    expect(getAdminStats).not.toHaveBeenCalled();
  });
});
