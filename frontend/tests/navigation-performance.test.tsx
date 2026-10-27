import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { GlobalHeader } from "@/components/ui/global-header";
import { PersonalizationProvider, usePersonalization } from "@/features/personalization/personalization-provider";
import { useTranslation } from "@/lib/i18n/locale-provider";

const state = vi.hoisted(() => ({
  user: { id: "learner", role: "ADMIN", display_name: "Learner" },
  listNotifications: vi.fn(), getUnreadNotificationCount: vi.fn(),
}));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: state.user, loading: false, logout: vi.fn() }) }));
vi.mock("@/lib/api/notifications", () => ({ ...state, markNotificationRead: vi.fn(), markAllNotificationsRead: vi.fn() }));
vi.mock("next/link", () => ({ default: ({ prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean | null }) => <a {...props} data-prefetch={prefetch === false ? "disabled" : "automatic"} /> }));

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  state.user = { id: "learner", role: "ADMIN", display_name: "Learner" };
  state.listNotifications.mockResolvedValue([]); state.getUnreadNotificationCount.mockResolvedValue(3);
});

it("keeps the header and notification requests stable across ordinary route changes", async () => {
  const view = render(<GlobalHeader pathname="/library" />);
  await screen.findByRole("button", { name: "Notifications (3 unread)" });
  const header = screen.getByRole("banner");
  fireEvent.click(screen.getByRole("button", { name: "Menu" }));
  expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "true");
  view.rerender(<GlobalHeader pathname="/practice" />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false"));
  expect(state.listNotifications).toHaveBeenCalledTimes(1);
  expect(state.getUnreadNotificationCount).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("banner")).toBe(header);
  view.rerender(<GlobalHeader pathname="/library" />);
  expect(screen.getByRole("button", { name: "Menu" })).toHaveAttribute("aria-expanded", "false");
  // A new account must still get a fresh notification state.
  state.user = { ...state.user, id: "another-learner" };
  view.rerender(<GlobalHeader pathname="/practice" />);
  await waitFor(() => expect(state.getUnreadNotificationCount).toHaveBeenCalledTimes(2));
});

it("does not rerender translated consumers for unrelated appearance changes", () => {
  const translated = vi.fn();
  function Probe() { const { t } = useTranslation(); translated(); return <p>{t("shell.library")}</p>; }
  function Controls() { const { setAppearance } = usePersonalization(); return <button onClick={() => setAppearance("DARK")}>Dark</button>; }
  render(<PersonalizationProvider><Controls /><Probe /></PersonalizationProvider>);
  const baseline = translated.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(translated).toHaveBeenCalledTimes(baseline);
});

it("prefetches catalog navigation only on intent and leaves sensitive routes disabled", () => {
  render(<GlobalHeader pathname="/history" />);
  const library = screen.getByRole("link", { name: "Test library" });
  const practice = screen.getByRole("link", { name: "Skill practice" });
  expect(library).toHaveAttribute("data-prefetch", "disabled");
  expect(practice).toHaveAttribute("data-prefetch", "disabled");
  fireEvent.mouseEnter(library); fireEvent.focus(practice);
  expect(library).toHaveAttribute("data-prefetch", "automatic");
  expect(practice).toHaveAttribute("data-prefetch", "automatic");
  for (const name of ["Attempt history", "Analytics", "Builder", "Transfer", "Moderation", "Classrooms"])
    expect(screen.getByRole("link", { name })).toHaveAttribute("data-prefetch", "disabled");
});

it("respects a connection's save-data preference for intent prefetch", () => {
  Object.defineProperty(navigator, "connection", { configurable: true, value: { saveData: true } });
  try {
    render(<GlobalHeader pathname="/history" />);
    const library = screen.getByRole("link", { name: "Test library" });
    fireEvent.mouseEnter(library); fireEvent.focus(library);
    expect(library).toHaveAttribute("data-prefetch", "disabled");
  } finally { Reflect.deleteProperty(navigator, "connection"); }
});
