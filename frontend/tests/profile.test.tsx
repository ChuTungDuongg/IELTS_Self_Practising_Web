import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProfilePage from "@/app/profile/page";
import { AppShell } from "@/components/ui/app-shell";
import { AuthProvider } from "@/features/auth/auth-provider";
import { changePassword, getCurrentUser } from "@/lib/api/auth";
import { getProfile, updateProfile } from "@/lib/api/profile";
import { ApiError } from "@/lib/api/client";

const navigation = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/profile",
  useRouter: () => ({ replace: navigation.replace, push: vi.fn(), refresh: navigation.refresh }),
}));
vi.mock("@/lib/api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/auth")>()), getCurrentUser: vi.fn(), changePassword: vi.fn(),
}));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn(), updateProfile: vi.fn() }));

const base = {
  id: "11111111-1111-4111-8111-111111111111", email: "student@example.com",
  display_name: "Student", role: "USER" as const, is_active: true, email_verified: true,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", last_login_at: null,
  phone_number: null, date_of_birth: null, country: null, city: null, occupation: null,
  institution: null, target_band: null, target_listening_band: null, target_reading_band: null,
  target_writing_band: null, target_speaking_band: null, target_test_date: null, bio: null,
  has_password: true,
};

function view() {
  return render(<AuthProvider><AppShell><ProfilePage /></AppShell></AuthProvider>);
}

describe("profile", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(getCurrentUser).mockResolvedValue(base);
    vi.mocked(getProfile).mockResolvedValue(base);
  });

  it.each(["USER", "ADMIN"] as const)("renders read-only account details for %s", async (role) => {
    vi.mocked(getCurrentUser).mockResolvedValue({ ...base, role });
    vi.mocked(getProfile).mockResolvedValue({ ...base, role });
    view();
    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
    expect(screen.getByText("student@example.com")).toBeInTheDocument();
    expect(screen.getByText(role, { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Never")).toBeInTheDocument();
    expect(screen.queryByLabelText(/profile photo|profile picture|avatar/i)).not.toBeInTheDocument();
    expect(document.querySelector('input[type="file"]')).toBeNull();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Role")).not.toBeInTheDocument();
  });

  it("saves only changed fields and refreshes the header identity", async () => {
    vi.mocked(updateProfile).mockResolvedValue({ ...base, display_name: "New Name", city: "Hanoi", target_listening_band: 8 });
    vi.mocked(getCurrentUser).mockResolvedValueOnce(base).mockResolvedValueOnce({ ...base, display_name: "New Name" });
    view();
    await screen.findByLabelText("City");
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New Name" } });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Hanoi" } });
    fireEvent.change(screen.getByLabelText("Listening"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith({ display_name: "New Name", city: "Hanoi", target_listening_band: 8 }));
    expect(await screen.findByRole("status")).toHaveTextContent("Profile saved.");
    expect(await screen.findByRole("link", { name: /New Name/ })).toHaveAttribute("href", "/profile");
    expect(getCurrentUser).toHaveBeenCalledTimes(2);
  });

  it("shows all IELTS goals with saved values and half-band input limits", async () => {
    vi.mocked(getProfile).mockResolvedValue({
      ...base, target_band: 7.5, target_listening_band: 8,
      target_reading_band: 7.5, target_writing_band: 7, target_speaking_band: 7,
      target_test_date: "2026-12-05",
    });
    view();
    expect(await screen.findByText("Overall target band")).toBeInTheDocument();
    expect(screen.queryByLabelText("Overall target band")).not.toBeInTheDocument();
    expect(screen.getByText("Overall target band").parentElement).toHaveTextContent("7.5");
    for (const [label, value] of [
      ["Listening", 8], ["Reading", 7.5],
      ["Writing", 7], ["Speaking", 7],
    ] as const) {
      const input = await screen.findByLabelText(label);
      expect(input).toHaveValue(value);
      expect(input).toHaveAttribute("type", "number");
      expect(input).toHaveAttribute("min", "0");
      expect(input).toHaveAttribute("max", "9");
      expect(input).toHaveAttribute("step", "0.5");
    }
    expect(screen.getByLabelText("Target test date")).toHaveValue("2026-12-05");
  });

  it("shows backend-derived Overall and updates it from the saved response", async () => {
    const goals = {
      ...base, target_band: 7, target_listening_band: 6, target_reading_band: 6.5,
      target_writing_band: 7.5, target_speaking_band: 8.5,
    };
    vi.mocked(getProfile).mockResolvedValue(goals);
    vi.mocked(updateProfile).mockResolvedValue({ ...goals, target_band: 7.5, target_listening_band: 8 });
    view();
    const overall = (await screen.findByText("Overall target band")).parentElement;
    expect(overall).toHaveTextContent("7.0");
    expect(screen.queryByLabelText("Overall target band")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Listening"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith({ target_listening_band: 8 }));
    await waitFor(() => expect(overall).toHaveTextContent("7.5"));
  });

  it("shows no Overall until all four skill targets exist", async () => {
    vi.mocked(getProfile).mockResolvedValue({ ...base, target_listening_band: 8, target_reading_band: 7.5, target_writing_band: 7 });
    view();
    const overall = (await screen.findByText("Overall target band")).parentElement;
    expect(overall).toHaveTextContent("—");
    expect(screen.getByLabelText("Speaking")).toHaveValue(null);
  });

  it("sends only one edited skill, then null when that skill is cleared", async () => {
    const goals = { ...base, target_listening_band: 8, target_reading_band: 7.5 };
    vi.mocked(getProfile).mockResolvedValue(goals);
    vi.mocked(updateProfile).mockResolvedValueOnce({ ...goals, target_reading_band: 8 }).mockResolvedValueOnce({ ...goals, target_reading_band: null });
    view();
    const reading = await screen.findByLabelText("Reading");
    fireEvent.change(reading, { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(updateProfile).toHaveBeenNthCalledWith(1, { target_reading_band: 8 }));
    fireEvent.change(reading, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(updateProfile).toHaveBeenNthCalledWith(2, { target_reading_band: null }));
    expect(changePassword).not.toHaveBeenCalled();
  });

  it("reports an API failure", async () => {
    vi.mocked(updateProfile).mockRejectedValue(new Error("Save failed"));
    view();
    await screen.findByLabelText("City");
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Hanoi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed");
  });

  it("redirects unauthenticated visitors", async () => {
    vi.mocked(getCurrentUser).mockRejectedValue(new ApiError("AUTHENTICATION_REQUIRED", "Sign in", 401));
    view();
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/login?next=/profile"));
  });

  it("shows a separate password form only for local-password accounts", async () => {
    const first = view();
    expect(await screen.findByRole("heading", { name: "Security" })).toBeInTheDocument();
    for (const name of ["Current password", "New password", "Confirm new password"]) {
      expect(screen.getByLabelText(name)).toHaveAttribute("type", "password");
    }
    expect(screen.getByLabelText("Current password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("New password")).toHaveAttribute("autocomplete", "new-password");
    first.unmount();
    vi.mocked(getProfile).mockResolvedValue({ ...base, has_password: false });
    view();
    expect(await screen.findByText(/signs in through Google/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change password" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Current password")).not.toBeInTheDocument();
  });

  it("checks confirmation, rotates the session, clears fields, and keeps the user logged in", async () => {
    vi.mocked(changePassword).mockResolvedValue({ user: base, access_expires_at: "2026-01-01T00:00:00Z" });
    view();
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "old-password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "different-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("New passwords do not match.");
    expect(changePassword).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    await waitFor(() => expect(changePassword).toHaveBeenCalledWith({ current_password: "old-password", new_password: "new-password" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Password changed successfully.");
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.getByLabelText("Confirm new password")).toHaveValue("");
    expect(screen.getByRole("link", { name: /Student/ })).toHaveAttribute("href", "/profile");
    expect(getCurrentUser).toHaveBeenCalledTimes(2);
  });

  it("shows a structured current-password error without clearing entered values", async () => {
    vi.mocked(changePassword).mockRejectedValue(new ApiError("CURRENT_PASSWORD_INVALID", "The current password is incorrect.", 400));
    view();
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "wrong-password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The current password is incorrect.");
    expect(screen.getByLabelText("New password")).toHaveValue("new-password");
  });

  it("does not send password fields with Save profile", async () => {
    vi.mocked(updateProfile).mockResolvedValue({ ...base, city: "Hanoi" });
    view();
    await screen.findByLabelText("Current password");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "old-password" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password" } });
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Hanoi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith({ city: "Hanoi" }));
    expect(changePassword).not.toHaveBeenCalled();
  });
});
