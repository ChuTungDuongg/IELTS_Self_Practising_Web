import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/ui/app-shell";
import Link from "next/link";
import { renderWithLocale } from "./locale-test-utils";

const state = vi.hoisted(() => ({ pathname: "/", role: null as "USER" | "TEACHER" | "ADMIN" | null, loading: false, sessionError: null as string | null, name: "Learner", logout: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: state.role ? { role: state.role, display_name: state.name } : null, loading: state.loading, sessionError: state.sessionError, logout: state.logout }) }));
vi.mock("next/link", () => ({ default: ({ prefetch, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { prefetch?: boolean | null }) => <a {...props} data-prefetch={prefetch === false ? "disabled" : "automatic"} /> }));

const routes = ["/", "/library", "/practice", "/history", "/analytics", "/admin", "/admin/tests", "/transfer", "/admin/moderation", "/admin/classrooms"];
beforeEach(() => { state.pathname = "/"; state.role = null; state.loading = false; state.sessionError = null; state.name = "Learner"; window.localStorage.clear(); document.documentElement.dataset.theme = "light"; });

describe("horizontal application shell", () => {
  it.each(["/", "/library", "/practice", "/history", "/analytics", "/classrooms", "/admin"])("keeps the GMT+7 clock visible on %s", path => {
    state.pathname = path; state.role = "ADMIN";
    render(<AppShell currentYear={2026}>Content</AppShell>);
    expect(within(screen.getByRole("banner")).getByLabelText(/Vietnam time: .*GMT\+7/)).toBeInTheDocument();
  });
  it("links the compact BandPilot lockup to home", () => {
    render(<AppShell currentYear={2026}>Content</AppShell>);
    const brand = screen.getByRole("link", { name: "BandPilot home" });
    expect(brand).toHaveAttribute("href", "/");
    expect(brand).toHaveTextContent("BandPilot");
    expect(brand.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("banner")).not.toHaveTextContent("IELTS Studio");
  });
  it.each([
    ["/", "standard"], ["/review/attempt", "standard"], ["/library/version", "standard"],
    ["/admin/users/user", "standard"], ["/admin/tests/test", "standard"], ["/admin/tests/new", "standard"],
    ["/profile", "standard"], ["/login", "standard"], ["/register", "standard"],
    ["/test-session/session", "standard"], ["/session/restore", "standard"], ["/ordinary/form", "standard"],
    ["/admin/users/user/edit", "standard"], ["/admin/ordinary-form", "standard"],
    ["/library", "wide"], ["/practice", "wide"], ["/history", "wide"], ["/analytics", "wide"],
    ["/admin", "wide"], ["/admin/users", "wide"], ["/admin/tests", "wide"], ["/admin/classrooms", "wide"], ["/transfer", "wide"],
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
    expect(footer).toHaveTextContent("© 2026 BandPilot");
    expect(within(footer).getByRole("link", { name: "LinkedIn" })).toHaveAttribute("href", "https://www.linkedin.com/in/duongchunguyen/");
    expect(within(footer).getByRole("link", { name: "Facebook" })).toHaveAttribute("href", "https://www.facebook.com/rendezvouss0344/");
    expect(within(footer).getByRole("link", { name: "Zalo" })).toHaveAttribute("href", "https://zalo.me/0367365703");
    if (path !== "/") expect(within(footer).queryByRole("group", { name: "Sphere animation" })).not.toBeInTheDocument();
    expect(container.querySelector(".app-content")?.nextElementSibling).toBe(footer);
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });

  it.each(["/admin/tests/test/versions/version/preview", "/admin/tests/test/versions/version/preview/"])("only exact Builder preview suppresses the global footer: %s", (path) => {
    state.pathname = path; state.role = "ADMIN";
    const { container } = render(<AppShell currentYear={2026}>Preview</AppShell>);
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(container.querySelector(".app-footer")).toBeNull();
  });

  it.each(["USER", "TEACHER", "ADMIN"] as const)("authenticated navigation preserves routes (%s)", (role) => {
    state.role = role;
    const { container } = render(<AppShell currentYear={2026}><p>Feature content</p></AppShell>);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(role === "ADMIN" ? routes : role === "USER" ? [...routes.slice(0, 5), "/classrooms"] : [...routes.slice(0, 5), "/teacher/tests", "/teacher/classrooms"]);
    expect(links[0]).toHaveAccessibleName("Home");
    if (role === "ADMIN") expect(links.map((link) => link.textContent)).toEqual(["Home", "Test library", "Skill practice", "Attempt history", "Analytics", "Admin", "Builder", "Transfer", "Moderation", "Classrooms"]);
    for (const link of links) expect(link).toHaveAttribute("data-prefetch", link.getAttribute("href") === "/" ? "automatic" : "disabled");
    expect(links[0]).toHaveAttribute("aria-current", "page");
    expect(nav.closest("header")).toBe(screen.getByRole("banner"));
    expect(container.querySelector("aside")).toBeNull();
    expect(screen.queryByText("Workspace")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Current section")).not.toBeInTheDocument();
    expect(screen.queryByText("Built for focus")).not.toBeInTheDocument();
  });

  it.each(["/", "/login", "/register"])("removes guest primary navigation and its empty menu on %s", pathname => {
    state.pathname = pathname;
    renderWithLocale(<AppShell currentYear={2026}>Content</AppShell>);
    const header = within(screen.getByRole("banner"));
    expect(header.queryByRole("navigation")).not.toBeInTheDocument();
    expect(header.queryByRole("button", { name: "Menu" })).not.toBeInTheDocument();
    expect(header.queryByRole("link", { name: "Overview" })).not.toBeInTheDocument();
    expect(header.getByRole("link", { name: "BandPilot home" })).toHaveAttribute("href", "/");
    expect(header.getByRole("link", { name: "Login" })).toHaveAttribute("href", "/login");
    expect(header.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
    expect(header.getByLabelText(/Vietnam time: .*GMT\+7/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(header.queryByRole("link", { name: "Tổng quan" })).not.toBeInTheDocument();
    expect(header.getByRole("link", { name: "Trang chủ BandPilot" })).toHaveAttribute("href", "/");
  });

  it.each(["USER", "TEACHER", "ADMIN"] as const)("localizes Home without replacing the link or active indicator for %s", role => {
    state.role = role;
    renderWithLocale(<AppShell currentYear={2026}>Content</AppShell>);
    const link = within(screen.getByRole("banner")).getByRole("link", { name: "Home" });
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByRole("link", { name: "Trang chủ" })).toBe(link);
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("keeps teacher Classrooms beside Builder in the same primary navigation", () => {
    state.role = "TEACHER";
    render(<AppShell currentYear={2026}>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/", "/library", "/practice", "/history", "/analytics", "/teacher/tests", "/teacher/classrooms"]);
    expect(links.slice(-2).map((link) => link.textContent)).toEqual(["Builder", "Classrooms"]);
    expect(screen.queryByRole("button", { name: /Use (dark|light) theme/ })).not.toBeInTheDocument();
  });

  it.each([["/admin", "/admin"], ["/admin/classrooms", "/admin/classrooms"], ["/admin/tests", "/admin/tests"], ["/admin/tests/test/versions/version/edit", "/admin/tests"], ["/transfer", "/transfer"], ["/profile", null], ["/review/id", null], ["/test-session/id", null]])("admin active matching is exact (%s)", (path, active) => {
    state.role = "ADMIN"; state.pathname = path!;
    render(<AppShell currentYear={2026}>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    expect(links.filter((link) => link.getAttribute("aria-current") === "page").map((link) => link.getAttribute("href"))).toEqual(active ? [active] : []);
  });

  it("admin Vietnamese navigation preserves all routes and link identity", () => {
    state.role = "ADMIN"; state.pathname = "/admin/tests/a";
    renderWithLocale(<AppShell currentYear={2026}>Content</AppShell>);
    const links = within(screen.getByRole("navigation", { name: "Primary" })).getAllByRole("link");
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    const translated = within(screen.getByRole("navigation", { name: "Chính" })).getAllByRole("link");
    expect(translated.map((link) => link.textContent)).toEqual(["Trang chủ", "Thư viện đề", "Luyện từng kỹ năng", "Lịch sử luyện tập", "Thống kê", "Quản trị", "Biên soạn đề", "Chuyển đề", "Duyệt nội dung", "Lớp học"]);
    expect(translated.map((link) => link.getAttribute("href"))).toEqual(routes);
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    expect(screen.getByRole("banner").querySelector(".app-header-inner")).toContainElement(translated[0]);
    expect(screen.queryByRole("button", { name: "Dùng giao diện tối" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đăng xuất" })).toBeInTheDocument();
    translated.forEach((link, index) => expect(link).toBe(links[index]));
    expect(translated[6]).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it.each(["/attempt/id", "/attempt/id/paused", "/attempt/id/terminal"])("attempt routes bypass global chrome (%s)", (path) => {
    state.pathname = path; state.role = "ADMIN";
    const { container } = render(<AppShell currentYear={2026}><p>Attempt questions</p></AppShell>);
    expect(container.firstElementChild).toHaveClass("exam-shell");
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
    expect(within(screen.getByRole("banner")).queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Menu" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Login" })).not.toBeInTheDocument();
    if (mode === "error") expect(screen.getByRole("alert")).toHaveTextContent("Session unavailable");
  });

  it.each(["USER", "ADMIN"] as const)("keeps authenticated personalization and account action order (%s)", (role) => {
    state.role = role;
    state.name = "A very long fictional learner display name that must remain fully accessible";
    const { container } = render(<AppShell currentYear={2026}>Content</AppShell>);
    const actions = container.querySelector(".header-actions")!;
    const header = within(screen.getByRole("banner"));
    expect(header.queryAllByRole("button", { name: /^(English|Tiếng Việt|EN|VI)$/ })).toHaveLength(0);
    expect(header.queryByRole("group", { name: "Language" })).not.toBeInTheDocument();
    expect(header.queryAllByText(/^(EN|VI)$/)).toHaveLength(0);
    expect(header.queryByRole("button", { name: "Use dark theme" })).not.toBeInTheDocument();
    expect(Array.from(actions.children).map((child) => child.tagName.toLowerCase())).toEqual(role ? ["time", "button", "a", "button"] : ["time", "a", "a"]);
    expect(header.getByLabelText(/Vietnam time: .*GMT\+7/)).toBeVisible();
    if (role) expect(screen.getByRole("link", { name: new RegExp(state.name) })).toHaveAttribute("href", "/profile");
  });

  it.each(["/login", "/register", "/library"])("only exposes guest quick preferences on the homepage, excluding %s", pathname => {
    state.pathname = pathname;
    render(<AppShell currentYear={2026}>Content</AppShell>);
    expect(screen.queryByRole("group", { name: "Language" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use dark theme" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Login" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
  });

  it("retains one global nav and ordinary DOM Tab order without responsive duplicate controls", () => {
    state.role = "ADMIN";
    const { container } = renderWithLocale(<AppShell currentYear={2026}><input aria-label="Feature input" /></AppShell>);
    const header = screen.getByRole("banner");
    const focusable = Array.from(header.querySelectorAll<HTMLAnchorElement | HTMLButtonElement>('a[href], button'));
    expect(header.querySelectorAll("nav")).toHaveLength(1);
    expect(focusable.slice(1, 1 + routes.length).map((node) => node.getAttribute("href"))).toEqual(routes);
    expect(focusable.slice(1 + routes.length).map((node) => node.getAttribute("aria-label") ?? node.textContent)).toEqual(["Personalization", expect.stringContaining("Learner"), "Logout", "Menu"]);
    expect(focusable.every((node) => node.tabIndex === 0)).toBe(true);
    expect(container.querySelector('[tabindex]:not([tabindex="0"]):not([tabindex="-1"])')).toBeNull();
  });
});
