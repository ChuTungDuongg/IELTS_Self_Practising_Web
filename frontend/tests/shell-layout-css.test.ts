import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss, { type Rule } from "postcss";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
const stylesheet = postcss.parse(css);
const desktop = "(width >= 1440px)";
const medium = "(768px <= width < 1440px)";
const small = "(width < 768px)";

function declarations(selector: string, media?: string): Record<string, string> {
  const result: Record<string, string> = {};
  stylesheet.walkRules((rule) => {
    const query = rule.parent?.type === "atrule" ? rule.parent.params : undefined;
    if (query === media && rule.selector.split(",").map((item) => item.trim()).includes(selector)) {
      rule.walkDecls((decl) => { result[decl.prop] = decl.value; });
    }
  });
  return result;
}

function atWidth(selector: string, width: number): Record<string, string> {
  return { ...declarations(selector), ...declarations(selector, width >= 1440 ? desktop : width >= 768 ? medium : small) };
}

describe("shell layout contracts", () => {
  it("caps centered border-box content and chrome at their approved outer widths", () => {
    expect(declarations(".app-content-standard")["max-width"]).toBe("1280px");
    expect(declarations(".app-content-wide")["max-width"]).toBe("1440px");
    for (const selector of [".app-content", ".app-header-inner", ".app-footer-inner"]) {
      expect(declarations(selector)).toMatchObject({ "box-sizing": "border-box", width: "100%", margin: "0 auto" });
    }
    for (const selector of [".app-header-inner", ".app-footer-inner"]) expect(declarations(selector)["max-width"]).toBe("1440px");
    expect(declarations(".app-shell")).toMatchObject({ display: "flex", "flex-direction": "column", "min-height": "100dvh" });
    const shell = stylesheet.nodes.find((node): node is Rule => node.type === "rule" && node.selector === ".app-shell")!;
    const heights: string[] = [];
    shell.walkDecls("min-height", (decl) => { heights.push(decl.value); });
    expect(heights).toEqual(["100vh", "100dvh"]);
    expect(declarations(".app-content").flex).toBe("1");
    expect(["fixed", "absolute"]).not.toContain(declarations(".app-footer").position);
  });

  it.each([[1920, "40px 32px 48px", "32px"], [1440, "40px 32px 48px", "32px"], [1439.5, "32px 24px 40px", "24px"], [768, "32px 24px 40px", "24px"], [767.5, "24px 16px 32px", "16px"], [320, "24px 16px 32px", "16px"]] as const)("uses approved main and chrome padding at %spx", (width, padding, horizontal) => {
    expect(atWidth(".app-content", width).padding).toBe(padding);
    for (const selector of [".app-header-inner", ".app-footer-inner"]) expect(atWidth(selector, width)["padding-inline"]).toBe(horizontal);
  });

  it("constrains descriptive prose and existing inner form bodies", () => {
    for (const selector of [".page-description", ".section-description", ".home-hero-description"]) expect(declarations(selector)["max-width"]).toBe("72ch");
    expect(declarations(".profile-form")["max-width"]).toBe("920px");
    expect(declarations(".app-content-standard > form.surface-card")["max-width"]).toBe("720px");
    const newTest = readFileSync(resolve(process.cwd(), "src/features/test-builder/new-test-form.tsx"), "utf8");
    expect(newTest).toContain('className="surface-card max-w-2xl');
    expect(declarations(".auth-card").width).toBe("min(100%, 480px)");
    expect(declarations(".session-transition").width).toBe("min(100%, 720px)");
  });

  it("header wraps at approved breakpoints", () => {
    const queries: string[] = [];
    stylesheet.walkAtRules("media", (rule) => { queries.push(rule.params); });
    expect(queries).toEqual(expect.arrayContaining([desktop, medium, small]));
    expect(declarations(".app-header")).toMatchObject({ position: "sticky", height: "auto", "min-height": "72px" });
    expect(atWidth(".app-header-inner", 1440)).toMatchObject({ display: "grid", "grid-template-areas": '"brand nav actions"', "grid-template-columns": "auto minmax(0, 1fr) auto" });
    expect(atWidth(".app-header-inner", 1000)).toMatchObject({ "grid-template-areas": '"brand actions" "nav nav"', "grid-template-columns": "minmax(0, 1fr) auto" });
    expect(atWidth(".app-header", 1000).position).toBe("sticky");
    expect(atWidth(".app-header-inner", 320)).toMatchObject({ "grid-template-areas": '"brand" "actions" "nav"', "grid-template-columns": "minmax(0, 1fr)" });
    expect(atWidth(".app-header", 320).position).toBe("static");
    expect(declarations(".brand")["grid-area"]).toBe("brand");
    expect(declarations(".primary-nav")["grid-area"]).toBe("nav");
    expect(declarations(".header-actions")["grid-area"]).toBe("actions");
    expect(declarations(".primary-nav-list")).toMatchObject({ "flex-wrap": "wrap", gap: "4px 8px" });
    expect(declarations(".header-actions")["flex-wrap"]).toBe("wrap");
    expect(atWidth(".app-footer-inner", 320)).toMatchObject({ "flex-direction": "column", gap: "12px" });
  });

  it("keeps long navigation labels and small actions reachable without clipping", () => {
    expect(declarations(".primary-nav-link")).toMatchObject({ "white-space": "normal", "overflow-wrap": "break-word", "min-height": "44px" });
    for (const selector of [".primary-nav", ".primary-nav-list", ".primary-nav-list li", ".header-actions"]) expect(declarations(selector)["min-width"]).toBe("0");
    stylesheet.walkRules((rule) => {
      if (rule.selector.split(",").some((selector) => /^\.(?:app-header|primary-nav|header-actions)/.test(selector.trim()))) {
        rule.walkDecls((decl) => {
          if (["overflow", "overflow-x"].includes(decl.prop)) expect(["hidden", "clip", "auto", "scroll"]).not.toContain(decl.value);
          if (decl.prop === "white-space") expect(decl.value).not.toBe("nowrap");
          if (decl.prop === "text-overflow") expect(decl.value).not.toBe("ellipsis");
          if (decl.prop === "height") expect(decl.value).toBe("auto");
        });
      }
    });
    expect(declarations(".auth-user-name")["max-width"]).toBe("120px");
    expect(atWidth(".auth-user-name", 320)["max-width"]).toBe("96px");
    for (const selector of [".header-actions a", ".header-actions button"]) expect(atWidth(selector, 320)["min-height"]).toBe("44px");
    for (const file of ["app-shell.tsx", "global-header.tsx"]) {
      const source = readFileSync(resolve(process.cwd(), "src/components/ui", file), "utf8");
      expect(source).not.toMatch(/innerWidth|matchMedia|ResizeObserver/);
    }
  });
});
