import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AdminUserPage from "@/app/admin/users/[userId]/page";
import { getAdminUser } from "@/lib/api/admin";

vi.mock("@/lib/api/admin", () => ({ getAdminUser: vi.fn() }));
vi.mock("@/lib/api/server-client", () => ({ serverApiRequest: vi.fn() }));
vi.mock("@/features/auth/admin-user-actions", () => ({ AdminUserActions: () => null }));

it("shows the derived Overall provided by the backend as read-only profile detail", async () => {
  const userId = "11111111-1111-4111-8111-111111111111";
  vi.mocked(getAdminUser).mockResolvedValue({
    user: {
      id: userId, email: "learner@example.com", display_name: "Learner",
      role: "USER", is_active: true, last_login_at: null,
      phone_number: null, date_of_birth: null, country: null, city: null,
      occupation: null, institution: null, bio: null, target_test_date: null,
      target_band: 7, target_listening_band: 6, target_reading_band: 6.5,
      target_writing_band: 7.5, target_speaking_band: 8.5,
    },
    history: { total: 0, items: [] },
    analytics: { total_finalized_attempts: 0, completed_full_mocks: 0 },
  } as never);
  render(await AdminUserPage({ params: Promise.resolve({ userId }) }));
  expect(screen.getByText("Overall target band").parentElement).toHaveTextContent("7");
  expect(screen.getByText("Speaking target band").parentElement).toHaveTextContent("8.5");
  expect(screen.queryByLabelText("Overall target band")).not.toBeInTheDocument();
});
