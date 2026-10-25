import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { transform } from "lightningcss";
import postcss from "postcss";
import { afterEach, describe, expect, it } from "vitest";

// Source-level cascade checks only. These exercise the conflicting legacy/new
// rules; they do not claim to measure browser layout, paint, or text overflow.
const source = ["globals.css", "design-system.css"].map(file => readFileSync(resolve(process.cwd(), "src/app", file), "utf8")).join("\n");
const css = postcss.parse(transform({ filename: "bandpilot.css", code: Buffer.from(source), targets: { chrome: 110 << 16 } }).code.toString());

function styles(element: Element, width: number) {
  const result: Record<string, string> = {};
  css.walkRules(rule => {
    let parent: postcss.AnyNode | undefined = rule.parent;
    while (parent) {
      if (parent.type === "atrule" && parent.name === "media") {
        const query = parent.params;
        if (/prefers-reduced-motion/.test(query)) return;
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
