import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const css = postcss.parse(readFileSync(resolve("src/features/classrooms/scheduling/calendar.css"), "utf8"));
function atWidth(selector: string, width: number) {
  const values: Record<string, string> = {};
  css.walkRules(rule => {
    if (!rule.selector.split(",").map(value => value.trim()).includes(selector)) return;
    if (rule.parent?.type === "atrule") {
      const limit = /max-width:\s*(\d+)px/.exec(rule.parent.params);
      if (limit && width > Number(limit[1])) return;
    }
    rule.walkDecls(decl => { values[decl.prop] = decl.value; });
  });
  return values;
}
it.each([375, 768, 1024, 1440])("contains the seven-column month grid and stacks details when needed at %spx", width => {
  expect(atWidth(".calendar-grid", width)["grid-template-columns"]).toBe("repeat(7, minmax(0, 1fr))");
  expect(atWidth(".calendar-layout", width)["grid-template-columns"]).toBe(width <= 1023 ? "minmax(0, 1fr)" : "minmax(0, 1fr) minmax(240px, 300px)");
  expect(atWidth(".calendar-surface", width)["min-width"]).toBe("0");
  expect(atWidth(".calendar-details", width)["min-width"]).toBe("0");
  expect(atWidth(".assignment-calendar .calendar-date", width)["min-height"]).toBe("44px");
  expect(atWidth(".calendar-event-chip span", width)["text-overflow"]).toBe("ellipsis");
});
it("uses semantic light/dark surfaces and distinguishes today, selection and event kinds without color alone", () => {
  expect(atWidth('.classroom-classwork .classroom-course-section[data-archived="true"]', 1440).background).toBe("var(--surface-soft)");
  expect(atWidth('.calendar-day[data-selected="true"]', 1440).background).toBe("var(--surface-hover)");
  expect(atWidth('.calendar-date[aria-current="date"]', 1440)["text-decoration"]).toBe("underline");
  expect(atWidth('.calendar-event-chip[data-kind="AVAILABLE"]', 1440)["border-left-style"]).toBe("dotted");
  expect(atWidth('.calendar-event-chip[data-kind="CUTOFF"]', 1440)["border-left-style"]).toBe("double");
});
