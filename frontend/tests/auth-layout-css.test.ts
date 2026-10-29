import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { transform } from "lightningcss";
import postcss from "postcss";
import { afterEach, describe, expect, it } from "vitest";

const source = readFileSync(resolve("src/features/auth/auth.module.css"), "utf8");
const css = postcss.parse(source.replace(/:global\(([^)]+)\)/g, "$1"));

// Source contracts, not browser layout measurements. Keep the phone form visible,
// the illustration contained, and the existing headline typography unchanged.
function styles(element: Element, width: number, reducedMotion = false) {
  const result: Record<string, string> = {};
  css.walkRules(rule => {
    const media = rule.parent?.type === "atrule" ? rule.parent.params : "";
    const boundary = media.match(/width < (\d+)px/);
    if (boundary && width >= Number(boundary[1])) return;
    if (media.includes("prefers-reduced-motion") && !reducedMotion) return;
    if (media.includes("forced-colors")) return;
    if (rule.selector.includes("::")) return;
    if (!element.matches(rule.selector)) return;
    rule.walkDecls(declaration => { result[declaration.prop] = declaration.value; });
  });
  return result;
}

function fixture() {
  document.documentElement.dataset.design = "editorial";
  document.documentElement.dataset.theme = "dark";
  document.body.innerHTML = '<main class="app-content"><div class="experience"><aside class="hero"><h2 class="title"></h2><ul class="features"></ul><div class="illustration"></div></aside><div class="formColumn"><section class="card"><form class="form"><div class="field"><input /><button class="passwordToggle"></button></div><button class="submit"></button></form></section></div></div></main><div class="exam-shell"><input /></div>';
  return (selector: string) => document.querySelector(selector)!;
}

afterEach(() => { document.body.replaceChildren(); delete document.documentElement.dataset.design; delete document.documentElement.dataset.theme; });

describe("auth presentation contracts", () => {
  it("compiles as a scoped CSS module without affecting exam surfaces", () => {
    const compiled = transform({ filename: "auth.module.css", code: Buffer.from(source), cssModules: { pure: true } });
    expect(compiled.warnings).toEqual([]);
    const find = fixture();
    expect(styles(find(".exam-shell"), 1440)).toEqual({});
    expect(styles(find(".exam-shell input"), 390)).toEqual({});
    expect(styles(find("main"), 1440)["max-width"]).toBe("none");
    find(".experience").remove();
    expect(styles(find("main"), 1440)).toEqual({});
  });

  it.each([320, 390, 768, 1024, 1440, 1700])("retains the original headline identity at %spx", width => {
    const find = fixture();
    expect(styles(find("h2"), width)).toMatchObject({
      "font-family": "var(--font-display)",
      "font-weight": "500",
      "letter-spacing": "-.055em",
      "line-height": "1.05",
    });
  });

  it.each([320, 390, 768, 820])("keeps a single form column and removes the large illustration at %spx", width => {
    const find = fixture();
    expect(styles(find(".experience"), width)["grid-template-columns"]).toBe("minmax(0, 1fr)");
    expect(styles(find(".illustration"), width).display).toBe("none");
    expect(styles(find(".formColumn"), width).display).toBe("grid");
    expect(styles(find(".card"), width).display).not.toBe("none");
    if (width < 768) expect(styles(find(".features"), width).display).toBe("none");
  });

  it.each([1024, 1440, 1700])("contains decorative layers and maintains two columns at %spx", width => {
    const find = fixture();
    expect(styles(find(".experience"), width)["grid-template-columns"]).not.toBe("minmax(0, 1fr)");
    expect(styles(find(".illustration"), width)).toMatchObject({ overflow: "clip", "pointer-events": "none" });
    expect(styles(find(".illustration"), width).display).not.toBe("none");
  });

  it("keeps touch targets, focus indicators, reduced motion and both theme palettes", () => {
    const find = fixture();
    expect(styles(find("input"), 390)["min-height"]).toBe("50px");
    expect(styles(find(".passwordToggle"), 390)).toMatchObject({ width: "44px", height: "44px" });
    expect(styles(find(".submit"), 390)["min-height"]).toBe("50px");
    expect(source).toContain(":focus-visible");
    expect(styles(find("input"), 390, true).transition).toBe("none");
    const dark = styles(find(".experience"), 1440);
    document.documentElement.dataset.theme = "light";
    const light = styles(find(".experience"), 1440);
    expect(dark["--auth-indigo"]).not.toBe(light["--auth-indigo"]);
    expect(styles(find(".card"), 1440).color).toBe("var(--ink)");
    expect(styles(find("input"), 1440).background).toContain("var(--surface)");
  });
});
