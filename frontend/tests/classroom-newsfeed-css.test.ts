import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";
const source = readFileSync(resolve("src/features/classrooms/content/stream/stream.css"), "utf8"), css = postcss.parse(source);
function atWidth(selector: string, width: number) {
  const values: Record<string, string> = {};
  css.walkRules(rule => {
    if (!rule.selector.split(",").map(value => value.trim()).includes(selector)) return;
    if (rule.parent?.type === "atrule") { const max = /max-width:\s*(\d+)px/.exec(rule.parent.params); if (max && width > Number(max[1])) return; }
    rule.walkDecls(decl => { values[decl.prop] = decl.value; });
  });
  return values;
}
it.each([375, 767, 768, 1024, 1100, 1440])("uses fluid feed/sidebar columns and readable wrapped controls at %spx", width => {
  expect(atWidth('.stream-layout[data-sidebar="true"]', width)["grid-template-columns"]).toBe(width >= 1100 ? "minmax(0, 2.25fr) minmax(0, 1fr)" : "minmax(0, 1fr)");
  expect(atWidth(".stream-main", width)["min-width"]).toBe("0");
  if (width <= 767) { expect(atWidth(".stream-sidebar", width)["grid-template-columns"]).toBe("minmax(0, 1fr)"); expect(atWidth(".stream-filters button", width)["min-height"]).toBe("44px"); }
  expect(atWidth(".stream-filters", width)["flex-wrap"]).toBe("wrap");
});
it("uses existing light/dark tokens, scoped selectors, and reduced-motion rules", () => {
  expect(source).not.toMatch(/#[0-9a-f]{3,8}\b|@import|\.exam-/i);
  css.walkDecls(decl => { expect(decl.prop.startsWith("--")).toBe(false); });
  expect(atWidth(".stream-sidebar-card", 1440).background).toBe("var(--surface)");
  expect(source).toContain("prefers-reduced-motion: reduce"); expect(source).toContain(":focus-visible");
  expect(atWidth(".stream-layout", 1440).gap).toBe("18px");
});
