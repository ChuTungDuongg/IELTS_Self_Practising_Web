import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

describe("exam theme CSS", () => {
  it("defines every custom property referenced by exam and highlight styles", () => {
    const definitions = new Set([...css.matchAll(/--([\w-]+)\s*:/g)].map((match) => match[1]));
    const relevant = css.slice(css.indexOf(".exam-runner"));
    const references = [...relevant.matchAll(/var\(--([\w-]+)/g)].map((match) => match[1]);

    expect([...new Set(references.filter((name) => !definitions.has(name)))]).toEqual([]);
    expect(relevant).not.toContain("var(--text)");
    expect(relevant).not.toContain("var(--foreground)");
  });

  it("uses semantic surface tokens instead of hardcoded light exam panels", () => {
    const examSection = css.slice(css.indexOf(".exam-runner"), css.indexOf("@media (max-width: 820px)"));

    expect(examSection).toContain("background: var(--exam-surface)");
    expect(examSection).toContain("background: var(--exam-surface-alt)");
    expect(examSection).not.toMatch(/background:\s*#(?:fff(?:fff)?|fafafa|f5f6f8)\b/i);
    expect(examSection).not.toMatch(/color:\s*#(?:1f2937|334155|475569|64748b)\b/i);
  });

  it("provides light and dark semantic exam tokens from the root theme", () => {
    const darkTheme = css.slice(css.indexOf(':root[data-theme="dark"]'), css.indexOf("* { box-sizing"));
    for (const token of ["exam-bg", "exam-surface", "exam-surface-alt", "exam-text", "exam-muted", "exam-border", "exam-control-bg", "exam-control-text", "exam-accent"]) {
      expect(css).toMatch(new RegExp(`--${token}:`));
      expect(darkTheme).toMatch(new RegExp(`--${token}:`));
    }
  });

  it("keeps Candidate Reading editorial and navigation states explicit", () => {
    expect(css).toMatch(/\.exam-passage\s*\{[^}]*background:\s*var\(--exam-surface\)/);
    expect(css).toMatch(/\.exam-questions\s*\{[^}]*background:\s*var\(--exam-surface-alt\)/);
    expect(css).toMatch(/\.exam-question-strip\s*\{[^}]*flex-wrap:\s*nowrap[^}]*overflow-x:\s*auto/);
    for (const state of ["answered", "unanswered", "flagged", "current"]) {
      expect(css).toContain(`.exam-question-chip.${state}`);
    }
  });

  it("preserves multiline instructions and compact inline completion gaps", () => {
    expect(css).toMatch(/\.question-group-instruction\s*>\s*p\s*\{[^}]*white-space:\s*pre-wrap/);
    expect(css).toMatch(/\.completion-gap-inline\s*\{[^}]*display:\s*inline-flex/);
    expect(css).toMatch(/\.completion-gap-input\s*\{[^}]*min-height:\s*32px/);
  });
});
