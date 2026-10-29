import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppFooter } from "@/components/ui/app-footer";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { renderWithLocale } from "./locale-test-utils";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("shared footer", () => {
  it("autoplays even with reduced motion and lets the user pause and resume the loop", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    renderWithLocale(<AppFooter year={2026} home />);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveAttribute("data-motion", "playing");
    expect(footer).toHaveAttribute("data-motion-paused", "false");
    fireEvent.click(screen.getByRole("button", { name: "Pause scrolling text" }));
    expect(footer).toHaveAttribute("data-motion", "paused");
    expect(footer).toHaveAttribute("data-motion-paused", "true");
    fireEvent.click(screen.getByRole("button", { name: "Resume scrolling text" }));
    expect(footer).toHaveAttribute("data-motion", "playing");
    expect(footer).toHaveAttribute("data-motion-paused", "false");
  });

  it("renders the homepage loop playing before hydration", () => {
    const markup = renderToString(<LocaleProvider><AppFooter year={2026} home /></LocaleProvider>);
    expect(markup).toContain('data-motion="playing"');
    expect(markup).toContain('data-motion-paused="false"');
    expect(markup).toContain("Pause scrolling text");
  });

  it("groups the original wordmark and copy beside navigation and the sphere card without duplicate branding", () => {
    renderWithLocale(<AppFooter year={2031} home />);
    const footer = screen.getByRole("contentinfo");
    const showcase = footer.querySelector(".gravity-footer-top")!;
    const brand = showcase.querySelector(".gravity-footer-signature")!;
    const side = showcase.querySelector(".gravity-footer-side")!;
    const bottom = footer.querySelector(".gravity-footer-bottom")!;
    const wordmark = brand.querySelector("p.gravity-wordmark");
    expect(wordmark).toHaveTextContent("BandPilot");
    expect(wordmark).toHaveAttribute("aria-hidden", "true");
    expect(footer.querySelectorAll(".gravity-wordmark")).toHaveLength(1);
    expect(footer.querySelector("strong")).toBeNull();
    expect(within(brand as HTMLElement).getByRole("heading", { name: "Your next step starts here." })).toBeInTheDocument();
    expect(within(brand as HTMLElement).getByText("Practice smarter. Reach your band.")).toHaveAttribute("lang", "en");
    expect(footer.querySelectorAll(".gravity-footer-copy")).toHaveLength(1);
    expect(footer.querySelector(".gravity-footer-atmosphere")).toHaveAttribute("aria-hidden", "true");
    expect(side.querySelector(".gravity-motion-controls")).toBeInTheDocument();
    expect(footer.querySelectorAll(".gravity-motion-controls")).toHaveLength(1);
    expect(footer.querySelectorAll(".gravity-footer-ticker")).toHaveLength(1);
    expect(footer.firstElementChild).toHaveClass("gravity-footer-ticker");
    expect(footer.firstElementChild?.nextElementSibling).toBe(showcase);
    expect(showcase.nextElementSibling).toBe(bottom);
    expect(bottom.querySelectorAll(".footer-contacts")).toHaveLength(1);
    expect(bottom).toHaveTextContent("© 2031 BandPilot");
    expect(bottom.querySelector("strong")).toBeNull();
    expect([...side.querySelectorAll(".gravity-footer-navigation a")].map(link => link.getAttribute("href"))).toEqual(["/practice", "/library", "/history", "/analytics"]);
    for (const link of side.querySelectorAll<HTMLAnchorElement>(".gravity-footer-navigation a")) {
      expect(link.tabIndex).toBe(0);
      link.focus(); expect(link).toHaveFocus();
    }
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(within(brand as HTMLElement).getByRole("heading", { name: "Bước tiếp theo bắt đầu ở đây." })).toBeInTheDocument();
    expect(brand).toHaveTextContent("Luyện tập và biên soạn đề");
    expect(bottom).toHaveTextContent("Kết nối với tôi");
    expect(bottom).toHaveTextContent("Tiếng Việt");
    expect(footer.querySelectorAll(".gravity-wordmark")).toHaveLength(1);
  });

  it("preserves the signature wordmark and marquee CSS typography contracts", () => {
    const css = postcss.parse(readFileSync(resolve("src/app/gravity-home.css"), "utf8"));
    function declarations(selector: string) {
      const result: Record<string, string> = {};
      css.walkRules(rule => {
        if (rule.selector !== selector) return;
        rule.walkDecls(declaration => { result[declaration.prop] = declaration.value; });
      });
      return result;
    }
    expect(declarations(".gravity-footer .gravity-wordmark")).toMatchObject({
      "font-family": "var(--font-display)", "font-size": "clamp(48px, 7.5vw, 112px)",
      "font-weight": "600", "line-height": "1.15", "letter-spacing": "-.055em",
    });
    expect(declarations(".gravity-footer-ticker").padding).toBe("18px 0");
    expect(declarations(".gravity-footer-ticker > div").animation).toBe("gravity-ticker var(--ticker-duration, 26s) linear infinite");
    expect(declarations(".gravity-footer-ticker span")).toMatchObject({
      "font-family": "var(--font-display)", "font-size": "clamp(18px, 1.8vw, 26px)",
      "font-weight": "500", "line-height": "1.3", "letter-spacing": "-.02em", "white-space": "nowrap",
    });
  });

  it("shows product information, current language and contact links without sphere controls on ordinary pages", () => {
    renderWithLocale(<AppFooter year={2026} />);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent("BandPilot");
    expect(footer).not.toHaveTextContent("IELTS Studio");
    expect(within(footer).getByText("Practice smarter. Reach your band.")).toHaveAttribute("lang", "en");
    expect(footer).toHaveTextContent("Practice & authoring");
    expect(footer).toHaveTextContent("© 2026 BandPilot");
    expect(within(footer).getByText("English")).toHaveAttribute("lang", "en");
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByRole("contentinfo")).toBe(footer);
    expect(footer).toHaveTextContent("Luyện tập và biên soạn đề");
    expect(footer).toHaveTextContent("Practice smarter. Reach your band.");
    expect(within(footer).getByText("Tiếng Việt")).toHaveAttribute("lang", "vi");
    expect(footer.querySelectorAll("a")).toHaveLength(4);
    expect(footer.querySelector("button, select")).toBeNull();
    expect(footer.querySelector(".gravity-footer-top, .gravity-wordmark, .gravity-footer-ticker, .footer-contacts-showcase")).toBeNull();
    expect(footer).toHaveTextContent("Kết nối với tôi");
  });

  it.each([false, true])("uses the supplied social destinations and recognizable local icons (home=%s)", home => {
    renderWithLocale(<AppFooter year={2026} home={home} />);
    const footer = within(screen.getByRole("contentinfo"));
    const contacts = [
      ["LinkedIn", "https://www.linkedin.com/in/duongchunguyen/"],
      ["Facebook", "https://www.facebook.com/rendezvouss0344/"],
      ["Zalo", "https://zalo.me/0367365703"],
    ];
    for (const [name, url] of contacts) {
      const link = footer.getByRole("link", { name });
      expect(link).toHaveAttribute("href", url);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
      expect(link.tabIndex).toBe(0);
      expect(link.querySelector("svg")).toHaveAttribute("data-brand", name);
      expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
      if (home) expect(link.querySelector(".footer-social-name")).toHaveTextContent(name);
      else expect(link.querySelector(".footer-social-name")).toBeNull();
    }
    expect(footer.getByRole("link", { name: "Zalo" }).querySelector("text")).toHaveTextContent("Zalo");
    expect(footer.getByRole("link", { name: "0367365703" })).toHaveAttribute("href", "tel:+84367365703");
  });

  it.each([false, true])("uses the server year consistently through English hydration and Vietnamese restoration (home=%s)", async home => {
    window.localStorage.setItem("ielts-locale", "vi");
    const tree = <LocaleProvider><AppFooter year={2026} home={home} /></LocaleProvider>;
    const markup = renderToString(tree);
    expect(markup).toContain("© 2026 BandPilot");
    expect(markup).toContain("Practice &amp; authoring");
    expect(markup).toContain("English");
    const container = document.createElement("div");
    container.innerHTML = markup;
    document.body.append(container);
    const recoverable = vi.fn();
    let root: ReturnType<typeof hydrateRoot>;
    await act(async () => { root = hydrateRoot(container, tree, { onRecoverableError: recoverable }); });
    expect(container).toHaveTextContent("© 2026 BandPilot");
    expect(container).toHaveTextContent("Luyện tập và biên soạn đề");
    expect(recoverable).not.toHaveBeenCalled();
    await act(async () => root!.unmount());
    container.remove();
  });

  it("keeps the footer in normal flow below a growing main", () => {
    const css = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));
    function values(selector: string) {
      const result: Record<string, string> = {};
      css.nodes.forEach((node) => { if (node.type === "rule" && node.selector === selector) node.walkDecls((decl) => { result[decl.prop] = decl.value; }); });
      return result;
    }
    expect(values(".app-shell")).toMatchObject({ display: "flex", "flex-direction": "column", "min-height": "100dvh" });
    expect(values(".app-content").flex).toBe("1");
    expect(values(".app-footer").display).toBe("flex");
    expect(["fixed", "absolute"]).not.toContain(values(".app-footer").position);
  });
});
