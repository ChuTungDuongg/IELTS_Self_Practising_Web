import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import Link from "next/link";
import { renderWithLocale } from "./locale-test-utils";

const state = vi.hoisted(() => ({ pathname: "/", role: null as "USER" | "ADMIN" | null, loading: false, sessionError: null as string | null, name: "Learner", logout: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: state.role ? { role: state.role, display_name: state.name } : null, loading: state.loading, sessionError: state.sessionError, logout: state.logout }) }));
vi.mock("next/link", () => ({ default: ({ prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean | null }) => <a {...props} data-prefetch={prefetch === false ? "disabled" : "automatic"} /> }));

const routes = ["/", "/library", "/practice", "/history", "/analytics", "/admin", "/admin/tests", "/transfer"];
beforeEach(() => { state.pathname = "/"; state.role = null; state.loading = false; state.sessionError = null; state.name = "Learner"; window.localStorage.clear(); document.documentElement.dataset.theme = "light"; });

describe("horizontal application shell", () => {
  it.each([
    ["/", "standard"], ["/review/attempt", "standard"], ["/library/version", "standard"],
    ["/admin/users/user", "standard"], ["/admin/tests/test", "standard"], ["/admin/tests/new", "standard"],
    ["/profile", "standard"], ["/login", "standard"], ["/register", "standard"],
    ["/test-session/session", "standard"], ["/session/restore", "standard"], ["/ordinary/form", "standard"],
    ["/admin/users/user/edit", "standard"], ["/admin/ordinary-form", "standard"],
    ["/library", "wide"], ["/practice", "wide"], ["/history", "wide"], ["/analytics", "wide"],
    ["/admin", "wide"], ["/admin/users", "wide"], ["/admin/tests", "wide"], ["/transfer", "wide"],
    ["/admin/tests/test/versions/version/edit", "wide"], ["/admin/tests/test/versions/version/preview", "wide"],
    ["/admin/tests/new/", "standard"], ["/admin/tests/test/", "standard"], ["/library/", "wide"],
    ["/library/version/", "standard"], ["/admin/tests/test/versions/version/preview/", "wide"],
  ])("page family selects the approved width (%s → %s)", (path, width) => {
    state.pathname = path;
    render(<AppShell currentYear={2026}>Feature content</AppShell>);
    const main = screen.getByRole("main");
    expect(main).toHaveClass("app-content", `app-content-${width}`);
    expect(main).not.toHaveClass(`app-content-${width === "wide" ? "standard" : "wide"}`);
  });

  it.each(["/", "/admin", "/admin/tests", "/admin/tests/new", "/admin/tests/test", "/admin/tests/test/versions/version/edit", "/review/attempt", "/test-session/session", "/session/restore", "/login", "/register", "/profile", "/transfer", "/admin/tests/preview", "/admin/tests/preview/versions/version/edit", "/admin/tests/test/versions/version/preview/extra", "/admin/tests/test/versions/version/previewing", "/some/preview", "/admin/tests/test/preview", "/admin/tests/test/versions/version/preview//"])("only exact Builder preview suppresses the global footer: ordinary %s retains it", (path) => {
    state.pathname = path; state.role = "ADMIN";
    const { container } = render(<AppShell currentYear={2026}>Content</AppShell>);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveClass("app-footer");
    expect(footer).toHaveTextContent("© 2026 IELTS Studio");
    expect(container.querySelector(".app-content")?.nextElementSibling).toBe(footer);
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it.each(["/admin/tests/test/versions/version/preview", "/admin/tests/test/versions/version/preview/"])("only exact Builder preview suppresses the global footer: %s", (path) => {
    state.pathname = path; state.role = "ADMIN";
    const { container } = render(<AppShell currentYear={2026}>Preview</AppShell>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(container.querySelector(".app-footer")).toBeNull();
  });

  it.each([null, "USER", "ADMIN"] as const)("guest user and admin navigation preserve routes (%s)", (role) => {
    state.role = role;
    const { container } = render(<AppShell currentYear={2026}><p>Feature content</p></AppShell>);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(routes.slice(0, role === "ADMIN" ? 8 : role === "USER" ? 5 : 1));
    for (const link of links) expect(link).toHaveAttribute("data-prefetch", link.getAttribute("href") === "/" ? "automatic" : "disabled");
    expect(links[0]).toHaveAttribute("aria-current", "page");
    expect(nav.closest("header")).toBe(screen.getByRole("banner"));
    expect(container.querySelector("aside")).toBeNull();
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Current section")).not.toBeInTheDocument();
    expect(screen.queryByText("Built for focus")).not.toBeInTheDocument();
    if (!role) {
      expect(screen.getByRole("link", { name: "Login" })).toHaveAttribute("href", "/login");
      expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
    }
  });

  it.each([["/admin", "/admin"], ["/admin/tests", "/admin/tests"], ["/admin/tests/test/versions/version/edit", "/admin/tests"], ["/transfer", "/transfer"], ["/profile", null], ["/review/id", null], ["/test-session/id", null]])("admin active matching is exact (%s)", (path, active) => {
    state.role = "ADMIN"; state.pathname = path!;
    render(<AppShell currentYear={2026}>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    expect(links.filter((link) => link.getAttribute("aria-current") === "page").map((link) => link.getAttribute("href"))).toEqual(active ? [active] : []);
  });

  it("admin Vietnamese navigation preserves all routes and link identity", () => {
    state.role = "ADMIN"; state.pathname = "/admin/tests/a";
    renderWithLocale(<AppShell currentYear={2026}>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    const language = screen.getByRole("group", { name: "Language" });
    const english = within(language).getByRole("button", { name: "English" });
    const vietnamese = within(language).getByRole("button", { name: "Tiếng Việt" });
    expect(english).toHaveAttribute("lang", "en");
    expect(english).toHaveAttribute("aria-pressed", "true");
    expect(vietnamese).toHaveAttribute("lang", "vi");
    expect(vietnamese).toHaveTextContent("VI");
    expect(english).toHaveTextContent("EN");
    fireEvent.click(vietnamese);
    const translated = within(screen.getByRole("navigation", { name: "Chính" })).getAllByRole("link");
    expect(translated.map((link) => link.textContent)).toEqual(["Tổng quan", "Thư viện đề", "Luyện từng kỹ năng", "Lịch sử luyện tập", "Thống kê", "Quản trị", "Biên soạn đề", "Chuyển đề"]);
    expect(translated.map((link) => link.getAttribute("href"))).toEqual(routes);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    expect(screen.getByRole("banner").querySelector(".app-header-inner")).toContainElement(language);
    expect(screen.getByRole("banner").querySelector(".app-header-inner")).toContainElement(translated[0]);
    expect(screen.getByRole("button", { name: "Dùng giao diện tối" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeInTheDocument();
    translated.forEach((link, index) => expect(link).toBe(links[index]));
    expect(translated[6]).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("group", { name: "Ngôn ngữ" })).toBe(language);
    expect(vietnamese).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it.each(["/attempt/id", "/attempt/id/paused", "/attempt/id/terminal"])("attempt routes bypass global chrome (%s)", (path) => {
    state.pathname = path; state.role = "ADMIN";
    const { container } = render(<AppShell currentYear={2026}><p>Attempt questions</p></AppShell>);
    expect(screen.getByRole("main")).toHaveClass("exam-shell");
    expect(screen.getByText("Attempt questions")).toBeInTheDocument();
    expect(container.querySelector("header, footer, aside, nav")).toBeNull();
    expect(container.querySelector('[class*="app-content"], .app-shell')).toBeNull();
  });

  it("retains feature-local filters, navigation, tabs and back links", () => {
    state.role = "ADMIN"; state.pathname = "/practice";
    render(<AppShell currentYear={2026}><aside className="practice-filter-panel">Local filters</aside><nav className="builder-local-nav" aria-label="Builder workspace"><Link href="/admin/tests/test">Local Builder</Link></nav><div role="tablist" aria-label="Feature tabs"><button role="tab">Local tab</button></div><Link href="/library">Back to library</Link></AppShell>);
    expect(screen.getByText("Local filters")).toHaveClass("practice-filter-panel");
    expect(screen.getByRole("navigation", { name: "Builder workspace" })).toHaveClass("builder-local-nav");
    expect(screen.getByRole("tab", { name: "Local tab" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to library" })).toHaveAttribute("href", "/library");
  });

  it.each(["loading", "error"])("keeps conservative auth actions during %s", (mode) => {
    state.loading = mode === "loading"; state.sessionError = mode === "error" ? "Session unavailable" : null;
    render(<AppShell currentYear={2026}>Content</AppShell>);
    expect(within(screen.getByRole("navigation")).getAllByRole("link")).toHaveLength(1);
    expect(screen.queryByRole("link", { name: "Login" })).not.toBeInTheDocument();
    if (mode === "error") expect(screen.getByRole("alert")).toHaveTextContent("Session unavailable");
  });

  it.each([null, "USER"] as const)("keeps header actions in language theme account order (%s)", (role) => {
    state.role = role;
    state.name = "A very long fictional learner display name that must remain fully accessible";
    const { container } = render(<AppShell currentYear={2026}>Content</AppShell>);
    const actions = container.querySelector(".header-actions")!;
    expect(Array.from(actions.children).map((child) => child.getAttribute("role") ?? child.tagName.toLowerCase())).toEqual(["group", "button", "a", role ? "button" : "a"]);
    if (role) expect(screen.getByRole("link", { name: new RegExp(state.name) })).toHaveAttribute("href", "/profile");
  });

  it("retains one global nav and ordinary DOM Tab order without responsive duplicate controls", () => {
    state.role = "ADMIN";
    const { container } = renderWithLocale(<AppShell currentYear={2026}><input aria-label="Feature input" /></AppShell>);
    const header = screen.getByRole("banner");
    const focusable = Array.from(header.querySelectorAll<HTMLAnchorElement | HTMLButtonElement>('a[href], button'));
    expect(header.querySelectorAll("nav")).toHaveLength(1);
    expect(focusable.slice(1, 9).map((node) => node.getAttribute("href"))).toEqual(routes);
    expect(focusable.slice(9).map((node) => node.getAttribute("aria-label") ?? node.textContent)).toEqual(["English", "Tiếng Việt", "Use dark theme", expect.stringContaining("Learner"), "Logout"]);
    expect(focusable.every((node) => node.tabIndex === 0)).toBe(true);
    expect(container.querySelector('[tabindex]:not([tabindex="0"]):not([tabindex="-1"])')).toBeNull();
  });
});
