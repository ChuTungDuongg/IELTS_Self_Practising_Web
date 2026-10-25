import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss, { type Rule } from "postcss";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
const designCss = readFileSync(resolve(process.cwd(), "src/app/design-system.css"), "utf8");
const writingCss = readFileSync(resolve(process.cwd(), "src/features/writing/writing-ai-assessment.module.css"), "utf8");
const stylesheet = postcss.parse(css);
const designStylesheet = postcss.parse(designCss);
const darkSelector = ':root[data-theme="dark"]';

function declarations(source: postcss.Root, selector: string): Record<string, string> {
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  const rule = source.nodes.find((node): node is Rule => node.type === "rule" && normalize(node.selector) === normalize(selector));
  expect(rule, `missing ${selector}`).toBeDefined();
  const values: Record<string, string> = {};
  rule!.walkDecls((declaration) => { values[declaration.prop] = declaration.value; });
  return values;
}

const designRoot = designStylesheet.nodes.find((node): node is Rule => node.type === "rule" && node.selector === ':root[data-design="editorial"][data-theme]')!;
const designDark = designRoot.nodes.find((node): node is Rule => node.type === "rule" && node.selector === '&[data-theme="dark"]')!;
const directTokens = (rule: Rule): Record<string, string> => {
  const values: Record<string, string> = {};
  for (const node of rule.nodes) if (node.type === "decl" && node.prop.startsWith("--")) values[node.prop] = node.value;
  return values;
};
const light = { ...declarations(stylesheet, ":root"), ...directTokens(designRoot) };
const dark = { ...light, ...declarations(stylesheet, darkSelector), ...directTokens(designDark) };

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
  it("uses the current Gravity product palette with account and exam defaults", () => {
    const expected = {
  "light": {
    "app-bg": "#f5f7fc",
    "paper": "var(--app-bg)",
    "app-bg-elevated": "#edf1f9",
    "surface": "#ffffff",
    "surface-raised": "#ffffff",
    "surface-soft": "#f0f3fa",
    "surface-hover": "#e8edf7",
    "surface-glass": "var(--surface)",
    "ink": "#15213a",
    "ink-soft": "#3c4962",
    "muted": "#5e6c84",
    "line": "#dfe5f0",
    "line-strong": "#a7b5cb",
    "accent": "#5261a8",
    "accent-strong": "#434f90",
    "accent-soft": "#e7e9f3",
    "surface-tint": "#e7e9f3",
    "accent-contrast": "#ffffff",
    "reading": "#256d76",
    "accent-cyan": "#286f82",
    "listening": "#67518b",
    "accent-violet": "#725b91",
    "writing": "#885422",
    "success": "#206746",
    "success-soft": "#eaf4ee",
    "warning": "#805315",
    "warning-soft": "#fbf2df",
    "danger": "#a52d42",
    "danger-soft": "#fceef0",
    "danger-contrast": "#ffffff",
    "shadow-sm": "0 2px 8px rgb(29 48 92 / .04)",
    "shadow-md": "0 12px 32px rgb(29 48 92 / .1)",
    "shadow-lg": "0 24px 80px rgb(18 32 64 / .2)"
  },
  "dark": {
    "app-bg": "#0f1522",
    "paper": "var(--app-bg)",
    "app-bg-elevated": "#141e30",
    "surface": "#172034",
    "surface-raised": "#1c2940",
    "surface-soft": "#1b2940",
    "surface-hover": "#25344d",
    "surface-glass": "var(--surface)",
    "ink": "#edf2ff",
    "ink-soft": "#c7d2e8",
    "muted": "#a6b5cf",
    "line": "#2d3d58",
    "line-strong": "#6f83a3",
    "accent": "#a4afd9",
    "accent-strong": "#b5bfe2",
    "accent-soft": "#333748",
    "surface-tint": "#333748",
    "accent-contrast": "#201e1b",
    "reading": "#9bcbd0",
    "accent-cyan": "#94bac4",
    "listening": "#c1b3dc",
    "accent-violet": "#b4a4ce",
    "writing": "#dfbc91",
    "success": "#a0d5b4",
    "success-soft": "#24382b",
    "warning": "#e2c38a",
    "warning-soft": "#3b3222",
    "danger": "#efa9b5",
    "danger-soft": "#3d272e",
    "danger-contrast": "#211417",
    "shadow-sm": "0 2px 8px rgb(29 48 92 / .04)",
    "shadow-md": "0 12px 32px rgb(0 0 0 / .24)",
    "shadow-lg": "0 24px 80px rgb(0 0 0 / .36)"
  }
};
    for (const [theme, values] of [[light, expected.light], [dark, expected.dark]] as const) {
      for (const [token, value] of Object.entries(values)) expect(theme[`--${token}`], token).toBe(value);
      expect(theme["--glow-accent"]).toBe("none");
      expect(theme["--glow-violet"]).toBe("none");
    }
    expect(Object.keys(dark).sort()).toEqual(Object.keys(light).sort());
  });

  it.each([...workspaceSurfaces, ...examSurfaces])("keeps %s subdued in the dark theme", (token) => {
    const rgb = color(token);
    expect(Math.max(...rgb) - Math.min(...rgb)).toBeLessThanOrEqual(examSurfaces.includes(token) ? 26 : 70);
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

  it("removes ambient shell lighting and flat-card hover glows while retaining the brand orbit", () => {
    expect(css).not.toContain(".app-shell::before");
    const navigation = declarations(stylesheet, `${darkSelector} .primary-nav-link-active`);
    expect(navigation.background).toContain("var(--surface-raised)");
    expect(navigation.background).not.toContain("gradient");
    const hover = declarations(stylesheet, `${darkSelector} :is(.home-metric, .learning-path-card, .practice-card, .test-card):hover`);
    expect(hover.background).toBe("var(--surface-hover)");
    expect(hover["box-shadow"]).toBe("var(--shadow-sm)");
    for (const token of ["glow-accent", "glow-violet"]) expect(dark[`--${token}`]).toBe("none");
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
