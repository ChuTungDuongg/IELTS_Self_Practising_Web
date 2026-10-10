import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
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

const baseline = [
  {
    "--app-bg": "#f4f7ff",
    "--app-bg-elevated": "#edf2ff",
    "--surface": "#ffffff",
    "--surface-raised": "#ffffff",
    "--surface-soft": "#f7f8fe",
    "--surface-hover": "#eef2ff",
    "--surface-glass": "rgb(255 255 255 / 0.84)",
    "--ink": "#151d35",
    "--ink-soft": "#34405d",
    "--muted": "#687493",
    "--line": "#dde4f2",
    "--line-strong": "#c7d2e8",
    "--accent": "#465de8",
    "--accent-strong": "#3348cd",
    "--accent-soft": "#e7ebff",
    "--accent-violet": "#7957d5",
    "--accent-cyan": "#008eb9",
    "--accent-contrast": "#ffffff",
    "--success": "#087f62",
    "--success-soft": "#e9f8f3",
    "--warning": "#b96b12",
    "--warning-soft": "#fff5e7",
    "--danger": "#c4495f",
    "--danger-soft": "#fff0f3",
    "--danger-contrast": "#ffffff",
    "--shadow-sm": "0 1px 2px rgb(24 35 70 / 0.05), 0 7px 20px rgb(50 64 112 / 0.06)",
    "--shadow-md": "0 18px 46px rgb(45 59 112 / 0.11), 0 3px 10px rgb(30 41 77 / 0.05)",
    "--shadow-lg": "0 30px 80px rgb(24 32 68 / 0.2)",
    "--glow-accent": "0 16px 36px rgb(70 93 232 / 0.2)",
    "--glow-violet": "0 18px 44px rgb(121 87 213 / 0.18)",
    "--paper": "var(--app-bg)",
    "--surface-tint": "var(--accent-soft)",
    "--reading": "var(--accent-cyan)",
    "--listening": "var(--accent-violet)",
    "--writing": "#cb6d30",
    "--highlight-bg": "#f4dc86",
    "--highlight-text": "#252137"
  },
  {
    "--app-bg": "#10131b",
    "--app-bg-elevated": "#141922",
    "--surface": "#191f2a",
    "--surface-raised": "#202733",
    "--surface-soft": "#242c39",
    "--surface-hover": "#2a3342",
    "--surface-glass": "rgb(20 25 34 / 0.96)",
    "--ink": "#edf0f7",
    "--ink-soft": "#c8cedb",
    "--muted": "#a1abba",
    "--line": "#303a49",
    "--line-strong": "#647087",
    "--accent": "#9aa6e8",
    "--accent-strong": "#8996d8",
    "--accent-soft": "#272f43",
    "--accent-violet": "#b1a2cf",
    "--accent-cyan": "#8cbcc5",
    "--accent-contrast": "#11151d",
    "--success": "#8fc1a4",
    "--success-soft": "#1c302a",
    "--warning": "#d6b47b",
    "--warning-soft": "#332c20",
    "--danger": "#df9ca7",
    "--danger-soft": "#36252c",
    "--danger-contrast": "#21151a",
    "--shadow-sm": "0 1px 2px rgb(0 0 0 / 0.12)",
    "--shadow-md": "0 8px 24px rgb(0 0 0 / 0.18)",
    "--shadow-lg": "0 20px 56px rgb(0 0 0 / 0.32)",
    "--glow-accent": "0 2px 8px rgb(154 166 232 / 0.06)",
    "--glow-violet": "0 2px 8px rgb(177 162 207 / 0.05)",
    "--paper": "var(--app-bg)",
    "--surface-tint": "var(--accent-soft)",
    "--reading": "var(--accent-cyan)",
    "--listening": "var(--accent-violet)",
    "--writing": "#d5a17d",
    "--highlight-bg": "#cbb674",
    "--highlight-text": "#191820"
  }
];

it.each(["light", "dark"] as const)("paper tokens cannot change resolved exam colors or controls (%s)", (theme) => {
 const stylesheet=postcss.parse(css);
 const rootTokens: Record<string,string>={};
 const scoped: Record<string,string>={};
 stylesheet.walkRules(rule=>{
   if (rule.selector===":root" || (theme==="dark" && rule.selector===':root[data-theme="dark"]')) rule.walkDecls(decl=>{rootTokens[decl.prop]=decl.value;});
   if (rule.selector === (theme==="dark" ? ':root[data-theme="dark"] :is(.exam-shell, .exam-runner)' : ':is(.exam-shell, .exam-runner)')) rule.walkDecls(decl=>{scoped[decl.prop]=decl.value;});
 });
 const expected=baseline[theme==="dark"?1:0];
 const values={...rootTokens,...scoped};
 const resolve=(value: string, source: Record<string,string>):string=>value.replace(/var\((--[\w-]+)\)/g,(_,key)=>resolve(source[key],source));
 for(const [token,value] of Object.entries(expected)) expect(resolve(values[token],values),token).toBe(resolve(value,expected));
 expect(scoped["font-size"]).toBe("15px");
 expect(rootTokens["--exam-accent"]).toBe(theme==="dark" ? "#9aa6e8" : "#256ea5");
 expect(rootTokens["--exam-bg"]).toBe(theme==="dark" ? "#101319" : "#eef2f8");
 expect(rootTokens["--exam-control-text"]).toBe(theme==="dark" ? "#edf0f7" : "#172039");
 const examTokens = theme === "dark"
   ? ["#101319", "#191e27", "#1e242e", "#e8ecf3", "#a1abba", "#364050", "#2a3342", "#edf0f7", "#9aa6e8"]
   : ["#eef2f8", "#ffffff", "#f5f7fb", "#172039", "#626e88", "#d6deeb", "#ffffff", "#172039", "#256ea5"];
 ["bg", "surface", "surface-alt", "text", "muted", "border", "control-bg", "control-text", "accent"].forEach((token, index) => expect(rootTokens[`--exam-${token}`]).toBe(examTokens[index]));
 const preview=readFileSync(resolvePath("src/features/test-builder/draft-preview.tsx"),"utf8");
 const gate=readFileSync(resolvePath("src/features/exam/paused-attempt-gate.tsx"),"utf8");
 expect(preview).toContain('className="exam-runner draft-preview');
 expect(gate).toContain('className="paused-attempt-gate"');
 expect(css).toContain(':is(.exam-shell, .exam-runner)');
});
function resolvePath(path: string) { return resolve(process.cwd(),path); }

it("protects exam dialogs and highlight portals from workspace decoration", () => {
 const stylesheet = postcss.parse(css);
 const values = (selector: string) => {
   const result: Record<string, string> = {};
   stylesheet.walkRules(rule => { if (rule.selector === selector) rule.walkDecls(decl => { result[decl.prop] = decl.value; }); });
   return result;
 };
 expect(values(':is(.exam-shell, .exam-runner) .dialog-backdrop')["backdrop-filter"]).toBe("blur(8px)");
 expect(values(':root[data-theme="dark"] :is(.exam-shell, .exam-runner) .dialog-backdrop')["backdrop-filter"]).toBe("blur(4px)");
 expect(values('.highlight-popover')["--surface-raised"]).toBe("#ffffff");
 expect(values(':root[data-theme="dark"] .highlight-popover')["--surface-raised"]).toBe("#202733");
 expect(readFileSync(resolvePath("src/features/highlighting/selectable-text.tsx"), "utf8")).toContain("createPortal");
});
