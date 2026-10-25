import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GlobalHeader } from "@/components/ui/global-header";

vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: { id: "learner", role: "ADMIN", display_name: "Learner" }, loading: false, logout: vi.fn() }) }));
vi.mock("@/features/notifications/notification-center", () => ({ NotificationCenter: () => null }));
vi.mock("@/features/personalization/personalization-dialog", () => ({ PersonalizationDialog: () => null }));

describe("responsive navigation disclosure", () => {
  it("opens the existing navigation, focuses its first destination and restores focus on Escape", () => {
    render(<GlobalHeader pathname="/practice" />);
    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(nav.id).toBe(menu.getAttribute("aria-controls"));
    expect(within(nav).getAllByRole("link")[0]).toHaveFocus();
    expect(within(nav).getAllByRole("link")).toHaveLength(10);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
  });

  it("closes when a destination is selected and when the route changes", () => {
    const view = render(<GlobalHeader pathname="/practice" />);
    const menu = screen.getByRole("button", { name: "Menu" });
    fireEvent.click(menu);
    screen.getByRole("link", { name: "Attempt history" }).addEventListener("click", event => event.preventDefault(), { once: true });
    fireEvent.click(screen.getByRole("link", { name: "Attempt history" }));
    expect(menu).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(menu);
    view.rerender(<GlobalHeader pathname="/history" />);
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
    view.rerender(<GlobalHeader pathname="/practice" />);
    expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  });
});
