import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss, { type Rule } from "postcss";
import { expect, it } from "vitest";

const css = readFileSync(resolve("src/app/globals.css"), "utf8");
const sheet = postcss.parse(css);
function declarations(selector: string) {
  const rule = sheet.nodes.find((node): node is Rule => node.type === "rule" && node.selector === selector);
  expect(rule, selector).toBeDefined();
  const values: Record<string, string> = {};
  rule!.walkDecls(decl => { values[decl.prop] = decl.value; });
  return values;
}
function luminance(hex: string) {
  const channels = hex.slice(1).match(/../g)!.map(value => parseInt(value, 16) / 255);
  return channels.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
}
function contrast(a: string, b: string) {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + .05) / (low + .05);
}

it("the root preset controls generic accent tokens without changing semantic or module tokens", () => {
  const source = postcss.parse(css);
  const presets = new Set<string>();
  source.walkRules(rule => {
    for (const match of rule.selector.matchAll(/data-accent="([a-z]+)"/g)) presets.add(match[1]);
  });
  expect([...presets].sort()).toEqual(["amber", "blue", "cyan", "emerald", "green", "indigo", "orange", "pink", "purple", "red"]);
  source.walkRules(rule => {
    if (!rule.selector.includes("data-accent")) return;
    rule.walkDecls(decl => expect(decl.prop).not.toMatch(/^--(?:danger|success|warning|reading|listening|writing|exam)(?:-|$)/));
  });
});

it.each(["purple", "indigo", "blue", "cyan", "emerald", "green", "amber", "orange", "red", "pink"])("%s has legible button and hover labels in both modes", preset => {
  const palette = declarations(`:where([data-accent="${preset}"])`);
  for (const mode of ["light", "dark"]) {
    const foreground = mode === "dark" ? "#201e1b" : "#ffffff";
    expect(contrast(foreground, palette[`--palette-${mode}`])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(foreground, palette[`--palette-strong-${mode}`])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(palette[`--palette-${mode}`], mode === "dark" ? "#201e1b" : "#fcfaf5")).toBeGreaterThanOrEqual(3);
  }
});

it("Purple preserves the existing default palette", () => {
  const purple = declarations(':where([data-accent="purple"])');
  for (const mode of ["light", "dark"]) {
    const base = declarations(mode === "dark" ? ':root[data-theme="dark"]' : ":root");
    for (const [palette, token] of [[`--palette-${mode}`, "--accent"], [`--palette-strong-${mode}`, "--accent-strong"], [`--palette-soft-${mode}`, "--accent-soft"]]) expect(purple[palette]).toBe(base[token]);
  }
});

it("generic primary and section controls consume accent tokens, with visible selected and focus states", () => {
  expect(declarations(":root[data-theme][data-accent]")).toMatchObject({ "--accent": "var(--personal-accent)", "--accent-strong": "var(--personal-accent-strong)", "--accent-soft": "var(--personal-accent-soft)", "--accent-contrast": "var(--personal-accent-contrast)", "--focus-ring": "var(--accent)" });
  expect(declarations('.listening-section-navigation button.active')).toMatchObject({ background: "var(--accent)", color: "var(--accent-contrast)" });
  expect(declarations('.accent-option[aria-pressed="true"]')["border-color"]).toBe("var(--accent)");
  expect(declarations(':focus-visible:not(:where(.exam-shell *, .exam-runner *))')["outline-color"]).toBe("var(--accent)");
  expect(declarations(':root[data-theme][data-accent] :is(.exam-shell, .exam-runner, .highlight-popover)')["--accent"]).toBe("var(--personal-accent)");
});
