import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

function themeBlock(selector: string, endMarker: string): string {
  const start = css.indexOf(selector);
  const end = css.indexOf(endMarker, start);
  return css.slice(start, end);
}

describe("fantasy galaxy visual system", () => {
  it("defines the shared semantic tokens in both supported themes", () => {
    const light = themeBlock(":root {", ':root[data-theme="dark"]');
    const dark = themeBlock(':root[data-theme="dark"]', "* { box-sizing");
    const tokens = [
      "app-bg",
      "app-bg-elevated",
      "surface-hover",
      "surface-glass",
      "accent-violet",
      "accent-cyan",
      "danger-contrast",
      "glow-accent",
      "glow-violet",
    ];

    for (const token of tokens) {
      expect(light, `light theme is missing --${token}`).toContain(`--${token}:`);
      expect(dark, `dark theme is missing --${token}`).toContain(`--${token}:`);
    }
  });

  it("keeps interactions accessible and responsive through shared primitives", () => {
    for (const selector of [".btn-primary", ".btn-secondary", ".btn-ghost", ".btn-danger", ".icon-button"]) {
      expect(css).toContain(selector);
    }
    expect(css).toContain(":focus-visible");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("@media (max-width: 860px)");
    expect(css).toContain(".app-shell");
    expect(css).not.toMatch(/url\s*\(/i);
    expect(css).not.toMatch(/#(?:7c3aed|8b5cf6|a78bfa)/i);
    expect(css).toMatch(/\.btn-primary\s*\{[^}]*color:\s*var\(--accent-contrast\)/);
    expect(css).toMatch(/\.btn-danger\s*\{[^}]*color:\s*var\(--danger-contrast\)/);
  });

  it("styles the reusable planet brand mark without raster dependencies", () => {
    expect(css).toContain(".app-logo");
    expect(css).toMatch(/\.brand-mark\s*\{[^}]*width:\s*42px[^}]*height:\s*42px/);
    expect(css).toMatch(/\.brand-mark \.app-logo\s*\{[^}]*drop-shadow/);
    expect(css).toMatch(/@media \(max-width:\s*560px\)[\s\S]*?\.brand-mark\s*\{[^}]*width:\s*36px[^}]*height:\s*36px/);
  });

  it("uses quiet semantic review states and shared raised overlay surfaces", () => {
    expect(css).toMatch(/\.review-answer-correct\s*\{[^}]*background:\s*var\(--success-soft\)/);
    expect(css).toMatch(/\.review-answer-wrong\s*\{[^}]*background:\s*var\(--danger-soft\)/);
    expect(css).toMatch(/\.dialog-panel\s*\{[^}]*background:\s*var\(--surface-raised\)[^}]*box-shadow:\s*var\(--shadow-lg\)/);
    expect(css).toMatch(/\.highlight-popover\s*\{[\s\S]*?background:\s*var\(--surface-raised\)[\s\S]*?box-shadow:\s*var\(--shadow-md\)/);
  });

  it("includes narrow-screen review and Candidate layout safeguards", () => {
    const narrow = themeBlock("@media (max-width: 700px)", ".completion-editable-text:only-child");
    expect(narrow).toContain(".review-header");
    expect(narrow).toContain(".review-answer-details");
    expect(narrow).toContain(".exam-passage-content");
    expect(narrow).toContain(".exam-footer");
  });

  it("integrates responsive Writing and grouped history surfaces", () => {
    for (const selector of [
      ".btn-writing",
      ".writing-task-grid",
      ".writing-runner-layout",
      ".writing-response-textarea",
      ".writing-review-layout",
      ".history-tabs",
      ".history-group-grid",
      ".history-group-skill",
    ]) {
      expect(css).toContain(selector);
    }
    expect(css).toMatch(/\.writing-response-textarea\s*\{[^}]*width:\s*100%[^}]*resize:\s*vertical/);
    expect(css).toMatch(/@media \(max-width:\s*900px\)[\s\S]*?\.writing-runner-layout\s*\{[^}]*grid-template-columns:\s*1fr/);
    expect(css).toMatch(/@media \(max-width:\s*700px\)[\s\S]*?\.history-group-skill\s*\{[^}]*grid-template-columns:\s*1fr/);
  });

  it("uses readable contextual label and criterion assessment classes", () => {
    for (const selector of [
      ".authoring-eyebrow",
      ".test-type",
      ".practice-module-kicker",
      ".writing-task-kicker",
      ".writing-review-kicker",
      ".writing-response-kicker",
      ".review-result-label",
      ".writing-assessment-grid",
      ".writing-criteria-grid",
    ]) {
      expect(css).toContain(selector);
    }
    expect(css).toMatch(/\.authoring-eyebrow\s*\{[^}]*font-size:\s*14px[^}]*letter-spacing:\s*\.03em/);
    expect(css).toMatch(/\.writing-task-kicker[^\{]*\{[^}]*font-size:\s*13px/);
    expect(css).toMatch(/\.review-score \.review-result-label\s*\{[^}]*font-size:\s*13px[^}]*text-transform:\s*none/);
    expect(css).toMatch(/@media \(max-width:\s*520px\)[\s\S]*?\.writing-criteria-grid\s*\{[^}]*grid-template-columns:\s*1fr/);
  });
});
