import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/page";
import { getAdminStats } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { serverApiRequest } from "@/lib/api/server-client";
import { getHistory } from "@/lib/api/history";
import { getTests } from "@/lib/api/tests";
import { getProfile } from "@/lib/api/profile";

vi.mock("@/lib/api/admin", () => ({ getAdminStats: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/lib/api/history", () => ({ getHistory: vi.fn() }));
vi.mock("@/lib/api/tests", () => ({ getTests: vi.fn() }));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn() }));
vi.mock("@/features/auth/admin-only", () => ({ AdminOnly: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("@/components/home/interactive-planet", () => ({ InteractivePlanet: () => null }));

const user = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "admin@example.com", display_name: "Admin", role: "ADMIN" as const,
  is_active: true, created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z", last_login_at: null,
};
const profile = {
  ...user, email_verified: true, phone_number: null, date_of_birth: null,
  country: null, city: null, occupation: null, institution: null, bio: null,
  target_band: 7.5, target_listening_band: 8, target_reading_band: 7.5,
  target_writing_band: 7, target_speaking_band: 7, target_test_date: "2026-12-05",
  has_password: true,
};

describe("homepage metrics and personal IELTS goals", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getTests).mockResolvedValue([]);
    vi.mocked(getHistory).mockResolvedValue({ items: [], groups: [], sessions: [], total: 0 });
    vi.mocked(serverApiRequest).mockResolvedValue(user);
    vi.mocked(getAdminStats).mockResolvedValue({ total_users: 14, active_users: 12 } as never);
    vi.mocked(getProfile).mockResolvedValue(profile);
  });

  it("gives ADMIN exactly four workspace cards in the desktop four-column class", async () => {
    render(await DashboardPage());
    const metrics = screen.getByRole("region", { name: "Workspace summary" });
    expect(metrics).toHaveClass("home-metrics-admin");
    expect(within(metrics).getAllByRole("link")).toHaveLength(4);
    for (const label of ["Published", "Resumable", "Builder tests", "Users"]) {
      expect(within(metrics).getByText(label)).toBeInTheDocument();
    }
    expect(within(metrics).getByRole("link", { name: /14\s*Users\s*12 active/i })).toHaveAttribute("href", "/admin");
    expect(getAdminStats).toHaveBeenCalledWith(serverApiRequest);
  });

  it("gives USER exactly two cards without admin cards or placeholders", async () => {
    vi.mocked(serverApiRequest).mockResolvedValue({ ...user, role: "USER" });
    render(await DashboardPage());
    const metrics = screen.getByRole("region", { name: "Workspace summary" });
    expect(metrics).not.toHaveClass("home-metrics-admin");
    expect(within(metrics).getAllByRole("link")).toHaveLength(2);
    expect(within(metrics).queryByText("Builder tests")).not.toBeInTheDocument();
    expect(within(metrics).queryByText("Users")).not.toBeInTheDocument();
    expect(getAdminStats).not.toHaveBeenCalled();
  });

  it.each(["USER", "ADMIN"] as const)("shows %s their own complete targets", async (role) => {
    vi.mocked(serverApiRequest).mockResolvedValue({ ...user, role });
    render(await DashboardPage());
    const goals = screen.getByRole("region", { name: "IELTS goals" });
    expect(within(goals).getByText("Overall target band").parentElement).toHaveTextContent("7.5");
    for (const [skill, value] of [["Listening", "8.0"], ["Reading", "7.5"], ["Writing", "7.0"], ["Speaking", "7.0"]]) {
      expect(within(goals).getByText(`${skill} target`).parentElement).toHaveTextContent(value);
    }
    expect(goals).toHaveTextContent("05 Dec 2026");
    expect(within(goals).getByRole("link", { name: /Edit goals/ })).toHaveAttribute("href", "/profile");
    expect(getProfile).toHaveBeenCalledWith(serverApiRequest);
  });

  it("shows dashes for unset parts of a partial goal", async () => {
    vi.mocked(getProfile).mockResolvedValue({ ...profile, target_band: null, target_listening_band: null, target_writing_band: null, target_speaking_band: null, target_test_date: null });
    render(await DashboardPage());
    const goals = screen.getByRole("region", { name: "IELTS goals" });
    expect(within(goals).getByText("Listening target").parentElement).toHaveTextContent("—");
    expect(within(goals).getByText("Reading target").parentElement).toHaveTextContent("7.5");
    expect(within(goals).getByText("Overall target band").parentElement).toHaveTextContent("—");
    expect(goals).toHaveTextContent("Target test —");
  });

  it("renders the derived 7.0 Overall returned for four saved skill targets", async () => {
    vi.mocked(getProfile).mockResolvedValue({
      ...profile, target_band: 7, target_listening_band: 6,
      target_reading_band: 6.5, target_writing_band: 7.5, target_speaking_band: 8.5,
    });
    render(await DashboardPage());
    const goals = screen.getByRole("region", { name: "IELTS goals" });
    expect(within(goals).getByText("Overall target band").parentElement).toHaveTextContent("7.0");
    expect(within(goals).getByRole("link", { name: /Edit goals/ })).toHaveAttribute("href", "/profile");
  });

  it("shows a compact setup invitation when every goal is unset", async () => {
    vi.mocked(getProfile).mockResolvedValue({ ...profile, target_band: null, target_listening_band: null, target_reading_band: null, target_writing_band: null, target_speaking_band: null, target_test_date: null });
    render(await DashboardPage());
    const goals = screen.getByRole("region", { name: "Set your IELTS goal" });
    expect(goals).toHaveTextContent("Add target bands for each skill to keep your practice focused.");
    expect(within(goals).getByRole("link", { name: /Set goals/ })).toHaveAttribute("href", "/profile");
    expect(goals).not.toHaveTextContent("Listening target");
  });

  it("does not request or show private goals for an unauthenticated visitor", async () => {
    vi.mocked(serverApiRequest).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    render(await DashboardPage());
    expect(getAdminStats).not.toHaveBeenCalled();
    expect(getProfile).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: /IELTS goal/ })).not.toBeInTheDocument();
  });

  it("ignores an expired profile session but surfaces other profile errors", async () => {
    vi.mocked(getProfile).mockRejectedValueOnce(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    render(await DashboardPage());
    expect(screen.queryByRole("region", { name: /IELTS goal/ })).not.toBeInTheDocument();
    vi.mocked(getProfile).mockRejectedValueOnce(new ApiError("API_ERROR", "Profile failed", 500));
    await expect(DashboardPage()).rejects.toThrow("Profile failed");
  });

  it("surfaces session backend errors", async () => {
    vi.mocked(serverApiRequest).mockRejectedValue(new ApiError("API_ERROR", "Backend failed", 500));
    await expect(DashboardPage()).rejects.toThrow("Backend failed");
    expect(getProfile).not.toHaveBeenCalled();
  });
});
