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
  it("uses the complete approved paper and graphite palettes", () => {
    const expected = {
  "light": {
    "app-bg": "#f5f2eb",
    "paper": "#f5f2eb",
    "app-bg-elevated": "#eee9df",
    "surface": "#fcfaf5",
    "surface-raised": "#fffdf8",
    "surface-soft": "#eeeae1",
    "surface-hover": "#e8e3d9",
    "surface-glass": "#fcfaf5",
    "ink": "#292620",
    "ink-soft": "#4c473e",
    "muted": "#686155",
    "line": "#ddd6c9",
    "line-strong": "#8f8575",
    "accent": "#5261a8",
    "accent-strong": "#434f90",
    "accent-soft": "#e7e9f3",
    "surface-tint": "#e7e9f3",
    "accent-contrast": "#ffffff",
    "reading": "#286f82",
    "accent-cyan": "#286f82",
    "listening": "#725b91",
    "accent-violet": "#725b91",
    "writing": "#99562e",
    "success": "#277052",
    "success-soft": "#e7f0e9",
    "warning": "#8a581d",
    "warning-soft": "#f5ebd9",
    "danger": "#a83c50",
    "danger-soft": "#f7e8eb",
    "danger-contrast": "#ffffff",
    "shadow-sm": "0 1px 3px rgb(41 38 32 / 0.07)",
    "shadow-md": "0 4px 12px rgb(41 38 32 / 0.08)",
    "shadow-lg": "0 12px 32px rgb(41 38 32 / 0.16)"
  },
  "dark": {
    "app-bg": "#201e1b",
    "paper": "#201e1b",
    "app-bg-elevated": "#25221e",
    "surface": "#292622",
    "surface-raised": "#312d28",
    "surface-soft": "#35312c",
    "surface-hover": "#3c3731",
    "surface-glass": "#292622",
    "ink": "#f1ece2",
    "ink-soft": "#d2cbc0",
    "muted": "#b4aa9a",
    "line": "#494239",
    "line-strong": "#8d8070",
    "accent": "#a4afd9",
    "accent-strong": "#b5bfe2",
    "accent-soft": "#333748",
    "surface-tint": "#333748",
    "accent-contrast": "#201e1b",
    "reading": "#94bac4",
    "accent-cyan": "#94bac4",
    "listening": "#b4a4ce",
    "accent-violet": "#b4a4ce",
    "writing": "#d2ab8b",
    "success": "#a3c3ad",
    "success-soft": "#26372d",
    "warning": "#d5b887",
    "warning-soft": "#3b3022",
    "danger": "#dda4aa",
    "danger-soft": "#3c292d",
    "danger-contrast": "#201e1b",
    "shadow-sm": "0 1px 3px rgb(0 0 0 / 0.16)",
    "shadow-md": "0 4px 12px rgb(0 0 0 / 0.20)",
    "shadow-lg": "0 12px 32px rgb(0 0 0 / 0.30)"
  }
};
    for (const [theme, values] of [[light, expected.light], [dark, expected.dark]] as const) {
      for (const [token, value] of Object.entries(values)) expect(theme[`--${token}`], token).toBe(value);
      expect(theme["--glow-accent"]).toBe("var(--shadow-sm)");
      expect(theme["--glow-violet"]).toBe("var(--shadow-sm)");
    }
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
  });

  it.each([...workspaceSurfaces, ...examSurfaces])("keeps %s dark and neutral instead of saturated navy", (token) => {
    const rgb = color(token);
    expect(Math.max(...rgb) - Math.min(...rgb)).toBeLessThanOrEqual(26);
    expect(luminance(rgb)).toBeLessThan(.06);
  });

  it("distinguishes surface elevation and editorial panes without color pools", () => {
    for (const surfaces of [examSurfaces]) {
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
      const badge = color(accent).map((channel, index) => channel * .08 + color("surface")[index] * .92);
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
    expect(css).not.toContain(".app-shell::before");
    const navigation = declarations(stylesheet, `${darkSelector} .primary-nav-link-active`);
    expect(navigation.background).toContain("var(--surface-raised)");
    expect(navigation.background).not.toContain("gradient");
    const hover = declarations(stylesheet, `${darkSelector} :is(.home-metric, .learning-path-card, .practice-card, .test-card):hover`);
    expect(hover.background).toBe("var(--surface-hover)");
    expect(hover["box-shadow"]).toBe("var(--shadow-sm)");
    for (const token of ["glow-accent", "glow-violet"]) expect(dark[`--${token}`]).toBe("var(--shadow-sm)");
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

 it("keeps light workspace text, semantic tints and meaningful boundaries readable", () => {
   const rgb = (token: string): number[] => light[`--${token}`].slice(1).match(/../g)!.map(channel => parseInt(channel,16));
   for (const surface of workspaceSurfaces) {
     for (const text of ["ink", "ink-soft", "muted"]) expect(contrast(rgb(text), rgb(surface)), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
     const controls = declarations(stylesheet, ':is(.field, .select-field, .textarea-field, .auth-form input, .practice-search, .analytics-compare-controls select):not(:where(.exam-shell *, .exam-runner *))');
     expect(controls["border-color"]).toBe("var(--accent)");
     expect(contrast(rgb("accent"), rgb(surface))).toBeGreaterThanOrEqual(3);
     expect(contrast(rgb("accent"), rgb(surface))).toBeGreaterThanOrEqual(3);
   }
   for (const semantic of ["reading", "listening", "writing"]) {
     const tint = rgb(semantic).map((c,i)=>c*.08+rgb("surface")[i]*.92);
     expect(contrast(rgb(semantic),tint)).toBeGreaterThanOrEqual(4.5);
     expect(contrast(rgb("accent-contrast"),rgb(semantic))).toBeGreaterThanOrEqual(4.5);
   }
   for (const state of ["success", "warning", "danger"]) expect(contrast(rgb(state),rgb(`${state}-soft`))).toBeGreaterThanOrEqual(4.5);
 });
