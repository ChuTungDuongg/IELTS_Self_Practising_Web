import { renderToStaticMarkup } from "react-dom/server";
import { Children, type ReactElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RootLayout, { themeInitializationScript } from "@/app/layout";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { AuthProvider } from "@/features/auth/auth-provider";
import { AppShell } from "@/components/ui/app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("RootLayout theme initialization", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllGlobals(); window.localStorage.clear(); });

  it("keeps the server composition English/light with LocaleProvider above auth and a server year", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-10T12:00:00Z"));
    window.localStorage.setItem("ielts-locale", "vi");
    window.localStorage.setItem("ielts-theme", "dark");
    const layout = RootLayout({ children: <p>content</p> });
    const body = layout.props.children as ReactElement<{ children: ReactNode }>;
    const locale = Children.toArray(body.props.children)[1] as ReactElement<{ children: ReactElement<{ children: ReactNode }> }>;
    expect(locale.type).toBe(LocaleProvider);
    expect(locale.props.children.type).toBe(AuthProvider);
    const shell = locale.props.children.props.children as ReactElement<{ currentYear: number }>;
    expect(shell.type).toBe(AppShell);
    expect(shell.props.currentYear).toBe(2026);
    const markup = renderToStaticMarkup(layout);
    expect(markup).toContain('lang="en"');
    expect(markup).toContain('data-theme="light"');
    expect(markup).toContain("Use dark theme");
    expect(markup).toContain("© 2026 IELTS Studio");
    expect(markup).not.toContain("Dùng giao diện");
  });

  it.each(["light", "dark", null, "system", "invalid"])("bootstraps only a valid saved theme or light (%s), ignoring OS dark", (saved) => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    vi.spyOn(Storage.prototype, "getItem").mockReturnValue(saved);
    document.documentElement.dataset.theme = "dark";
    document.documentElement.lang = "vi";
    document.body.innerHTML = "<p>Preserve text</p>";
    const before = document.body.innerHTML;
    window.eval(themeInitializationScript);
    expect(document.documentElement.dataset.theme).toBe(saved === "dark" ? "dark" : "light");
    expect(document.documentElement.lang).toBe("vi");
    expect(document.body.innerHTML).toBe(before);
    expect(matchMedia).not.toHaveBeenCalled();
    expect(themeInitializationScript).not.toContain("matchMedia");
    expect(themeInitializationScript).not.toContain("ielts-locale");
  });

  it("selects light when reading the saved theme throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    document.documentElement.dataset.theme = "dark";
    expect(() => window.eval(themeInitializationScript)).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
  it("renders a deterministic server theme and a trusted inline bootstrap script", () => {
    const markup = renderToStaticMarkup(<RootLayout><p>content</p></RootLayout>);
    expect(markup).toContain('data-theme="light"');
    const layout = RootLayout({ children: <p>content</p> }) as ReactElement<{ children: ReactNode }>;
    const body = layout.props.children as ReactElement<{ children: ReactNode }>;
    const initialization = Children.toArray(body.props.children)[0] as ReactElement<{ id: string; dangerouslySetInnerHTML: { __html: string } }>;
    expect(initialization.type).toBe("script");
    expect(initialization.props.id).toBe("theme-initialization");
    expect(initialization.props.dangerouslySetInnerHTML.__html).toBe(themeInitializationScript);
    expect(markup).not.toContain("data-nscript");
    expect(themeInitializationScript).toContain('localStorage.getItem("ielts-theme")');
    expect(themeInitializationScript).not.toContain("Date.now");
  });

  it("does not execute localStorage while rendering on the server", () => {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
    Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => { throw new Error("server localStorage access"); } });
    expect(() => renderToStaticMarkup(<RootLayout><p>content</p></RootLayout>)).not.toThrow();
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
  });
});
