import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss, { type Rule } from "postcss";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
const writingCss = readFileSync(resolve(process.cwd(), "src/features/writing/writing-ai-assessment.module.css"), "utf8");
const stylesheet = postcss.parse(css);
const darkSelector = ':root[data-theme="dark"]';

function declarations(source: postcss.Root, selector: string): Record<string, string> {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  const rule = source.nodes.find((node): node is Rule => node.type === "rule" && normalize(node.selector) === normalize(selector));
  expect(rule, `missing ${selector}`).toBeDefined();
  const values: Record<string, string> = {};
  rule!.walkDecls((declaration) => { values[declaration.prop] = declaration.value; });
  return values;
}

const light = declarations(stylesheet, ":root");
const dark = declarations(stylesheet, darkSelector);

function color(token: string): number[] {
  const value = dark[`--${token}`];
  if (value.startsWith("var(")) return color(value.slice(6, -1));
  expect(value, token).toMatch(/^#[0-9a-f]{6}$/i);
  return value.slice(1).match(/../g)!.map((channel) => Number.parseInt(channel, 16));
}

function luminance(rgb: number[]): number {
  return rgb.map((channel) => channel / 255)
    .map((channel) => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4)
    .reduce((sum, channel, index) => sum + channel * [.2126, .7152, .0722][index], 0);
}

function contrast(foreground: number[], background: number[]): number {
  const [high, low] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (high + .05) / (low + .05);
}

const workspaceSurfaces = ["app-bg", "app-bg-elevated", "surface", "surface-raised", "surface-soft", "surface-hover"];
const examSurfaces = ["exam-bg", "exam-surface", "exam-surface-alt", "exam-control-bg"];

describe("editorial dark theme", () => {
  it("keeps the complete light palette frozen and defines every semantic token in dark mode", () => {
    expect(light).toMatchInlineSnapshot(`
      {
        "--accent": "#465de8",
        "--accent-contrast": "#ffffff",
        "--accent-cyan": "#008eb9",
        "--accent-soft": "#e7ebff",
        "--accent-strong": "#3348cd",
        "--accent-violet": "#7957d5",
        "--app-bg": "#f4f7ff",
        "--app-bg-elevated": "#edf2ff",
        "--danger": "#c4495f",
        "--danger-contrast": "#ffffff",
        "--danger-soft": "#fff0f3",
        "--exam-accent": "#256ea5",
        "--exam-bg": "#eef2f8",
        "--exam-border": "#d6deeb",
        "--exam-control-bg": "#ffffff",
        "--exam-control-text": "#172039",
        "--exam-muted": "#626e88",
        "--exam-surface": "#ffffff",
        "--exam-surface-alt": "#f5f7fb",
        "--exam-text": "#172039",
        "--glow-accent": "0 16px 36px rgb(70 93 232 / 0.2)",
        "--glow-violet": "0 18px 44px rgb(121 87 213 / 0.18)",
        "--highlight-bg": "#f4dc86",
        "--highlight-text": "#252137",
        "--ink": "#151d35",
        "--ink-soft": "#34405d",
        "--line": "#dde4f2",
        "--line-strong": "#c7d2e8",
        "--listening": "var(--accent-violet)",
        "--muted": "#687493",
        "--paper": "var(--app-bg)",
        "--reading": "var(--accent-cyan)",
        "--shadow-lg": "0 30px 80px rgb(24 32 68 / 0.2)",
        "--shadow-md": "0 18px 46px rgb(45 59 112 / 0.11), 0 3px 10px rgb(30 41 77 / 0.05)",
        "--shadow-sm": "0 1px 2px rgb(24 35 70 / 0.05), 0 7px 20px rgb(50 64 112 / 0.06)",
        "--success": "#087f62",
        "--success-soft": "#e9f8f3",
        "--surface": "#ffffff",
        "--surface-glass": "rgb(255 255 255 / 0.84)",
        "--surface-hover": "#eef2ff",
        "--surface-raised": "#ffffff",
        "--surface-soft": "#f7f8fe",
        "--surface-tint": "var(--accent-soft)",
        "--warning": "#b96b12",
        "--warning-soft": "#fff5e7",
        "--writing": "#cb6d30",
        "color-scheme": "light",
      }
    `);
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
    expect(dark["color-scheme"]).toBe("dark");
  });

  it.each([...workspaceSurfaces, ...examSurfaces])("keeps %s dark and neutral instead of saturated navy", (token) => {
    const rgb = color(token);
    expect(Math.max(...rgb) - Math.min(...rgb)).toBeLessThanOrEqual(26);
    expect(luminance(rgb)).toBeLessThan(.06);
  });

  it("distinguishes surface elevation and editorial panes without color pools", () => {
    for (const surfaces of [workspaceSurfaces, examSurfaces]) {
      const levels = surfaces.map((token) => luminance(color(token)));
      expect(levels).toEqual([...levels].sort((a, b) => a - b));
      expect(new Set(levels).size).toBe(levels.length);
    }
    expect(luminance(color("exam-surface-alt")) - luminance(color("exam-surface"))).toBeLessThan(.01);
  });

  it("keeps body, metadata, placeholders and feedback readable across dark surfaces", () => {
    for (const background of [...workspaceSurfaces, "accent-soft", "success-soft", "warning-soft", "danger-soft"]) {
      for (const foreground of ["ink", "ink-soft", "muted"]) {
        expect(contrast(color(foreground), color(background)), `${foreground} on ${background}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    for (const background of examSurfaces) {
      for (const foreground of ["exam-text", "exam-muted", "exam-control-text"]) {
        expect(contrast(color(foreground), color(background)), `${foreground} on ${background}`).toBeGreaterThanOrEqual(4.5);
      }
    }
    expect(declarations(stylesheet, `${darkSelector} input::placeholder,\n${darkSelector} textarea::placeholder`)).toEqual({ color: "var(--muted)", opacity: "1" });
  });

  it("keeps action labels, focus accents and module badges readable", () => {
    for (const accent of ["accent", "accent-strong", "reading", "listening", "writing", "exam-accent"]) {
      expect(contrast(color("accent-contrast"), color(accent)), accent).toBeGreaterThanOrEqual(4.5);
      expect(contrast(color(accent), color("surface-hover")), accent).toBeGreaterThanOrEqual(3);
      const badge = color(accent).map((channel, index) => channel * .12 + color("surface")[index] * .88);
      expect(contrast(color(accent), badge), `${accent} badge`).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(color("danger-contrast"), color("danger"))).toBeGreaterThanOrEqual(4.5);
    for (const surface of ["app-bg-elevated", "surface-raised", "exam-surface", "exam-surface-alt"]) {
      expect(contrast(color("line-strong"), color(surface)), `control border on ${surface}`).toBeGreaterThanOrEqual(3);
    }
    expect(declarations(stylesheet, `${darkSelector} :focus-visible`)["outline-color"]).toBe("var(--accent)");
    expect(declarations(stylesheet, `${darkSelector} .exam-runner :focus-visible`)["outline-color"]).toBe("var(--exam-accent)");
  });

  it("uses soft status backgrounds with readable state text", () => {
    for (const status of ["success", "warning", "danger"]) {
      const background = color(`${status}-soft`);
      expect(luminance(background)).toBeLessThan(.04);
      expect(Math.max(...background) - Math.min(...background)).toBeLessThanOrEqual(26);
      expect(contrast(color(status), background)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("removes ambient shell lighting and flat-card hover glows while retaining the planet", () => {
    expect(declarations(stylesheet, `${darkSelector} .app-shell::before`).background).toBe("none");
    const navigation = declarations(stylesheet, `${darkSelector} .sidebar-item-active`);
    expect(navigation.background).toContain("var(--surface-raised)");
    expect(navigation.background).not.toContain("gradient");
    const hover = declarations(stylesheet, `${darkSelector} :is(.home-metric, .learning-path-card, .practice-card, .test-card):hover`);
    expect(hover.background).toBe("var(--surface-hover)");
    expect(hover["box-shadow"]).toBe("var(--shadow-sm)");
    for (const token of ["glow-accent", "glow-violet"]) {
      const opacity = Number(dark[`--${token}`].match(/\/\s*([\d.]+)/)![1]);
      expect(opacity).toBeLessThanOrEqual(.06);
    }
    expect(css).toContain(".home-orbit-interactive.is-active .home-orbit-scene");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
  });

  it("limits the new treatments to dark visual properties, including Writing AI", () => {
    const overrides = postcss.parse(css.slice(css.indexOf("/* Dark-only treatments")));
    const visualProperties = new Set(["background", "color", "border-color", "box-shadow", "backdrop-filter", "opacity", "accent-color", "outline-color"]);
    overrides.walkRules((rule) => {
      expect(rule.selector).toContain(darkSelector);
      rule.walkDecls((declaration) => { expect(visualProperties.has(declaration.prop), declaration.prop).toBe(true); });
    });
    const writing = postcss.parse(writingCss);
    expect(declarations(writing, `:global(${darkSelector}) .panel`)["border-color"]).toBe("var(--line)");
    for (const selector of [".overall", ".card"]) {
      expect(declarations(writing, `:global(${darkSelector}) ${selector}`).background).toBe("var(--surface-raised)");
    }
  });
});
