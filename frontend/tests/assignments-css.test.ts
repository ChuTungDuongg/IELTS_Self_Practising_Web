import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const source = readFileSync(resolve("src/features/classrooms/assignments/assignments.css"), "utf8");
const css = postcss.parse(source);
function atWidth(selector: string, width: number) {
  const values: Record<string, string> = {};
  css.walkRules(rule => {
    if (!rule.selector.split(",").map(value => value.trim().replace(':root[data-design="editorial"][data-theme] ', "")).includes(selector)) return;
    if (rule.parent?.type === "atrule") {
      const max = /max-width:\s*(\d+)px/.exec(rule.parent.params), min = /min-width:\s*(\d+)px/.exec(rule.parent.params);
      if (max && width > Number(max[1]) || min && width < Number(min[1])) return;
    }
    rule.walkDecls(decl => { values[decl.prop] = decl.value; });
  });
  return values;
}
it.each([375, 768, 1024, 1100, 1440])("keeps fluid creation/list columns and wraps actions at %spx", width => {
  expect(atWidth('.assignments-layout[data-creation="true"]', width)["grid-template-columns"]).toBe(width >= 1100 ? "minmax(0, .29fr) minmax(0, .71fr)" : "minmax(0, 1fr)");
  expect(atWidth(".assignments-sections", width)["min-width"]).toBe("0");
  expect(atWidth(".assignments-row", width)["min-width"]).toBe("0");
  if (width <= 480) expect(atWidth(".assignments-row-actions", width)["flex-wrap"]).toBe("wrap");
  if (width <= 767) expect(atWidth(".assignments-tab .btn", width)["min-height"]).toBe("44px");
});
it("scopes colors to shared light/dark tokens and preserves reduced-motion behavior", () => {
  expect(source).not.toMatch(/#[0-9a-f]{3,8}\b|\.exam-/i);
  css.walkDecls(decl => { expect(decl.prop.startsWith("--")).toBe(false); });
  expect(atWidth(".assignments-page-icon", 1440).color).toBe("var(--listening)");
  expect(atWidth(".assignments-archive", 1440)["border-color"]).toContain("var(--danger)");
  expect(source).toContain("prefers-reduced-motion: reduce");
});
