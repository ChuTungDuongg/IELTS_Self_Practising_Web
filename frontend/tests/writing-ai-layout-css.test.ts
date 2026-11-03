import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const css = postcss.parse(readFileSync(resolve("src/features/writing/writing-ai-assessment.module.css"), "utf8"));

it.each([".feedback", ".card .feedbackList", ".panel blockquote p"])("lets %s fill the Writing card instead of leaving a narrow text column", selector => {
  css.walkRules(rule => {
    if (rule.selector !== selector) return;
    rule.walkDecls("max-width", decl => {
      expect(["none", "100%"]).toContain(decl.value);
    });
  });
});

// CSS contracts only; browser geometry is verified separately.
it.each([390, 768, 1440])("keeps Writing criterion cards in one fluid column at %spx", width => {
  const declarations: Record<string, string> = {};
  css.walkRules(rule => {
    if (rule.selector !== ".criteria") return;
    if (rule.parent?.type === "atrule") {
      const max = /max-width:\s*(\d+)px/.exec(rule.parent.params);
      const min = /min-width:\s*(\d+)px/.exec(rule.parent.params);
      if (max && width > Number(max[1]) || min && width < Number(min[1])) return;
    }
    rule.walkDecls(decl => { declarations[decl.prop] = decl.value; });
  });
  expect(declarations.display).toBe("grid");
  expect(declarations["grid-template-columns"]).toMatch(/^(?:1fr|minmax\(0, 1fr\))$/);
  expect(declarations.height).toBeUndefined();
  expect(declarations["grid-auto-rows"]).toBeUndefined();
});
