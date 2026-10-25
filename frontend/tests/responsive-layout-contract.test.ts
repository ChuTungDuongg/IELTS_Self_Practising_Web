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

  it("stacks the Gravity footer sections instead of inheriting the legacy flex row", () => {
    fixture('<div class="gravity-story"></div><footer class="app-footer gravity-footer"><div class="gravity-footer-ticker"><div><span>More purposeful practice</span></div></div><div class="gravity-footer-top"><h2>Next step</h2><div><a href="/practice">Practice</a></div></div><p class="gravity-wordmark">BandPilot</p><div class="app-footer-inner"></div></footer>');
    const footer = document.querySelector("footer")!;
    expect(styles(footer, 1280).display).toBe("block");
    expect(styles(footer, 390).display).toBe("block");
    expect(styles(document.querySelector(".gravity-footer-top")!, 390)["flex-direction"]).toBe("column");
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
