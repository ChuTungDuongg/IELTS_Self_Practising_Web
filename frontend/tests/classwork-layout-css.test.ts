import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const css = postcss.parse(readFileSync(resolve("src/features/classrooms/content/classroom-workspace.css"), "utf8"));
it.each([375, 480, 481, 600, 640])("separates archived resource viewing from its action menu at %spx", width => {
  const values: Record<string, string> = {};
  css.walkRules(rule => {
    if (!rule.selector.split(",").map(value => value.trim()).includes(".classroom-archived-row .classroom-resource-reader-compact > button")) return;
    if (rule.parent?.type === "atrule") {
      const limit = /max-width:\s*(\d+)px/.exec(rule.parent.params);
      if (limit && width > Number(limit[1])) return;
    }
    rule.walkDecls(decl => { values[decl.prop] = decl.value; });
  });
  expect(values["grid-row"]).toBe("2");
  expect(values["grid-column"]).toBe("1");
});
