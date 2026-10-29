import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { transform } from "lightningcss";
import postcss from "postcss";
import { afterEach, describe, expect, it } from "vitest";

// Source-level cascade checks only. These exercise the conflicting legacy/new
// rules; they do not claim to measure browser layout, paint, or text overflow.
const source = ["globals.css", "design-system.css", "gravity-home.css", "gravity-product.css"].map(file => readFileSync(resolve(process.cwd(), "src/app", file), "utf8")).join("\n");
const css = postcss.parse(transform({ filename: "bandpilot.css", code: Buffer.from(source), targets: { chrome: 110 << 16 } }).code.toString());

function globalThemeTokens(file: string): Set<string> {
  const root = postcss.parse(readFileSync(resolve(process.cwd(), "src/app", file), "utf8"));
  const tokens = new Set<string>();
  root.walkRules(rule => {
    if (rule.parent?.type !== "root" || !/^:root(?:\[[^\]]+\])*$/.test(rule.selector)) return;
    for (const node of rule.nodes ?? []) {
      if (node.type === "decl" && node.prop.startsWith("--")) tokens.add(node.prop);
      if (node.type === "rule" && node.selector === '&[data-theme="dark"]') {
        for (const nested of node.nodes ?? []) if (nested.type === "decl" && nested.prop.startsWith("--")) tokens.add(nested.prop);
      }
    }
  });
  return tokens;
}

function styles(element: Element, width: number, reducedMotion = false) {
  const result: Record<string, string> = {};
  css.walkRules(rule => {
    let parent: postcss.AnyNode | undefined = rule.parent;
    while (parent) {
      if (parent.type === "atrule" && parent.name === "media") {
        const query = parent.params;
        if (/prefers-reduced-motion/.test(query) && !reducedMotion) return;
        for (const [, operator, value] of query.matchAll(/width\s*(<=|>=|<|>)\s*([\d.]+)px/g)) {
          const boundary = Number(value);
          if (operator === "<=" && width > boundary || operator === ">=" && width < boundary || operator === "<" && width >= boundary || operator === ">" && width <= boundary) return;
        }
        for (const [, value, operator] of query.matchAll(/([\d.]+)px\s*(<=|<)\s*width/g)) {
          if (operator === "<=" && width < Number(value) || operator === "<" && width <= Number(value)) return;
        }
      }
      parent = parent.parent;
    }
    try {
      if (!element.matches(rule.selector)) return;
      rule.walkDecls(declaration => { result[declaration.prop] = declaration.value; });
    } catch { /* Browser-specific pseudo-elements cannot match these controls. */ }
  });
  return result;
}

afterEach(() => { document.body.replaceChildren(); delete document.documentElement.dataset.design; });
function fixture(markup: string) {
  document.documentElement.dataset.design = "editorial";
  document.documentElement.dataset.theme = "light";
  document.body.innerHTML = markup;
}

describe("responsive layout contracts", () => {
  it("assigns shared theme tokens to the design system instead of import-order overrides", () => {
    const foundations = globalThemeTokens("globals.css");
    const designSystem = globalThemeTokens("design-system.css");
    const product = globalThemeTokens("gravity-product.css");
    expect([...foundations].filter(token => designSystem.has(token))).toEqual([]);
    expect([...product]).toEqual([]);
    expect([...globalThemeTokens("gravity-home.css")]).toEqual([]);
  });
  it("preserves the Gravity palette in both themes", () => {
    const root = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/design-system.css"), "utf8"));
    const tokens = (theme: "light" | "dark") => {
      const values: Record<string, string> = {};
      root.walkRules(rule => {
        if (rule.parent?.type !== "root" || rule.selector !== ':root[data-design="editorial"][data-theme]') return;
        const darkRule = rule.nodes?.find(node => node.type === "rule" && node.selector === '&[data-theme="dark"]');
        const nodes = theme === "dark" ? (darkRule?.type === "rule" ? darkRule.nodes : []) : rule.nodes;
        for (const node of nodes ?? []) if (node.type === "decl") values[node.prop] = node.value;
      });
      return values;
    };
    expect(tokens("light")).toMatchObject({ "--app-bg": "#f5f7fc", "--surface": "#ffffff", "--ink": "#15213a", "--radius-card": "20px" });
    expect(tokens("dark")).toMatchObject({ "--app-bg": "#0f1522", "--surface": "#172034", "--ink": "#edf2ff" });
  });
  it("autoplays the ticker without removing the global reduced-motion reset elsewhere", () => {
    fixture('<div class="gravity-revealed"></div><footer class="gravity-footer" data-motion="playing"><div class="gravity-footer-ticker"><div></div></div></footer>');
    const footer = document.querySelector("footer")!;
    const track = document.querySelector(".gravity-footer-ticker > div")!;
    expect(styles(document.querySelector(".gravity-revealed")!, 390, true)["animation-iteration-count"]).toBe("1");
    expect(styles(track, 390, true)["animation-duration"]).toContain("--ticker-duration");
    expect(styles(track, 390, true)["animation-iteration-count"]).toBe("infinite");
    footer.dataset.motion = "paused";
    footer.dataset.motionPaused = "true";
    expect(styles(track, 390, true)["animation-duration"]).toContain("--ticker-duration");
    expect(styles(track, 390, true)["animation-play-state"]).toBe("paused");
  });

  it("keeps the Gravity footer in normal flow and stacks its two-column showcase on phones", () => {
    fixture('<div class="gravity-story"></div><footer class="app-footer gravity-footer"><div class="gravity-footer-ticker"><div><span>More purposeful practice</span></div></div><div class="gravity-footer-top"><div class="gravity-footer-signature"><h2>Next step</h2><p class="gravity-wordmark">BandPilot</p></div><div class="gravity-footer-side"><div class="gravity-footer-navigation"><a href="/practice">Practice</a></div></div></div><div class="app-footer-inner gravity-footer-bottom"></div></footer>');
    const footer = document.querySelector("footer")!;
    expect(styles(footer, 1280).display).toBe("block");
    expect(styles(footer, 390).display).toBe("block");
    expect(styles(document.querySelector(".gravity-footer-top")!, 390)["grid-template-columns"]).toBe("minmax(0, 1fr)");
    expect(styles(document.querySelector(".gravity-footer-top")!, 1280)["grid-template-columns"]).toContain("1.65fr");
    expect(styles(document.querySelector(".gravity-footer-ticker span")!, 1280)["max-width"]).toBe("none");
    expect(styles(document.querySelector(".gravity-footer-ticker span")!, 390)["white-space"]).toBe("nowrap");
    expect(styles(document.querySelector(".gravity-story")!, 1280).overflow).toBe("clip");
  });

  it("keeps the disclosure out of the desktop grid and available on phones", () => {
    fixture('<header class="app-header"><button class="navigation-toggle icon-button"></button></header>');
    const button = document.querySelector("button")!;
    expect(styles(button, 1280).display).toBe("none");
    expect(styles(button, 390).display).toBe("inline-flex");
  });

  it.each([390, 820, 1440])("does not reserve a guest navigation row and keeps footer controls in flow at %spx", width => {
    fixture('<header class="app-header" data-has-navigation="false"><div class="app-header-inner"></div></header><footer class="app-footer gravity-footer"><div class="gravity-footer-controls"><div class="gravity-motion-controls"><div class="gravity-motion-buttons"><button class="gravity-control">Pause</button></div></div></div><div class="app-footer-inner"><div class="footer-contacts"><ul class="footer-social-links"><li><a href="https://zalo.me/0367365703"><svg></svg></a></li></ul></div></div></footer>');
    expect(styles(document.querySelector(".app-header-inner")!, width)["grid-template-areas"]).not.toContain("nav");
    const controls = document.querySelector(".gravity-motion-controls")!;
    expect(styles(controls, width).position).not.toBe("absolute");
    expect(styles(controls, width).display).toBe("grid");
    expect(styles(document.querySelector(".gravity-motion-buttons")!, width)["flex-wrap"]).toBe("wrap");
    expect(Number.parseFloat(styles(document.querySelector(".gravity-control")!, width)["min-height"])).toBeGreaterThanOrEqual(44);
    expect(styles(document.querySelector(".footer-social-links a")!, width)).toMatchObject({ width: "auto", "min-width": "44px", "min-height": "44px" });
    expect(styles(document.querySelector(".gravity-footer-controls")!, width)["max-width"]).toBe("100%");
    expect(styles(document.querySelector(".footer-contacts")!, width)["--contact-ink"]).toBe("#e6edff");
    document.documentElement.dataset.theme = "dark";
    expect(styles(document.querySelector(".footer-contacts")!, width)["--contact-ink"]).toBe("#e6edff");
  });

  it.each([320, 390, 767, 768, 1024, 1280, 2048])("retains signature type and contains the footer composition at %spx", width => {
    fixture('<footer class="app-footer gravity-footer"><div class="gravity-footer-top"><div class="gravity-footer-signature"><div class="gravity-footer-atmosphere"></div><p class="gravity-wordmark">BandPilot</p></div><div class="gravity-footer-side"><div class="gravity-footer-navigation"></div><div class="gravity-motion-controls"><div class="gravity-motion-buttons"><button class="gravity-control"></button></div></div></div></div><div class="app-footer-inner gravity-footer-bottom"><div class="footer-contacts footer-contacts-showcase"></div><div class="footer-legal"></div></div></footer>');
    expect(styles(document.querySelector(".gravity-wordmark")!, width)).toMatchObject({
      "font-family": "var(--font-display)", "font-size": "clamp(48px, 7.5vw, 112px)",
      "font-weight": "600", "line-height": "1.15", "letter-spacing": "-.055em",
    });
    expect(styles(document.querySelector(".gravity-footer-top")!, width)).toMatchObject({ display: "grid", "max-width": "1920px" });
    expect(styles(document.querySelector(".gravity-footer-navigation")!, width)["grid-template-columns"]).toBe("repeat(2, minmax(0, 1fr))");
    expect(styles(document.querySelector(".gravity-footer-atmosphere")!, width)["pointer-events"]).toBe("none");
    expect(styles(document.querySelector(".gravity-footer-side")!, width)["min-width"]).toBe("0");
    expect(styles(document.querySelector(".gravity-motion-buttons")!, width)["flex-wrap"]).toBe("wrap");
    if (width < 768) {
      expect(styles(document.querySelector(".gravity-footer-top")!, width)["grid-template-columns"]).toBe("minmax(0, 1fr)");
      expect(styles(document.querySelector(".gravity-footer-bottom")!, width)["grid-template-columns"]).toBe("minmax(0, 1fr)");
      expect(styles(document.querySelector(".footer-legal")!, width)["grid-column"]).toBe("1");
    }
  });

  it("keeps tablet filters in one column inside their narrow sidebar", () => {
    fixture('<div class="practice-browser"><nav class="practice-filter-panel"></nav></div>');
    expect(styles(document.querySelector("nav")!, 800)["grid-template-columns"]).toBe("minmax(0, 1fr)");
  });

  it("gives Listening chips flexible number tracks and space for their flags", () => {
    fixture('<div class="listening-question-navigation"><div class="listening-section-questions"><div class="exam-question-chip"><button class="exam-question-flag"></button></div></div></div>');
    const chip = document.querySelector(".exam-question-chip")!;
    expect(styles(chip, 680)["grid-template-columns"]).toBe("minmax(0, 1fr) 32px");
    expect(styles(document.querySelector(".listening-section-questions")!, 680)["grid-template-columns"]).toBe("repeat(2, minmax(0, 1fr))");
  });
});
