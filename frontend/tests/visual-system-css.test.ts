import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { afterEach, describe, expect, it } from "vitest";

const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
const workspaceOnly = ':not(:where(.exam-shell, .exam-shell *, .exam-runner, .exam-runner *, .highlight-popover, .highlight-popover *))';
afterEach(() => { document.body.replaceChildren(); document.documentElement.dataset.theme = "light"; });
function workspaceValues(selector: string, media?: string) {
  const result: Record<string, string> = {};
  postcss.parse(css).walkRules(rule => {
    if (rule.parent?.type === "atrule" && rule.parent.params !== media) return;
    if (rule.parent?.type !== "atrule" && media) return;
    if (postcss.list.comma(rule.selector).includes(selector)) rule.walkDecls(decl => { result[decl.prop] = decl.value; });
  });
  return result;
}

// Apply matching source declarations for the requested interaction state. This
// checks the CSS contract; jsdom does not demonstrate browser pixel layout.
function interactionValues(element: Element, state: "hover" | "focus" | "reduced") {
  const values: Record<string, string> = {};
  const important = new Set<string>();
  postcss.parse(css).walkRules((rule) => {
    if (rule.parent?.type === "atrule" && !(state === "reduced" && rule.parent.params === "(prefers-reduced-motion: reduce)")) return;
    const matches = postcss.list.comma(rule.selector).some((selector) => {
      if (selector.includes("::")) return false;
      if (selector.includes(":hover") && state !== "hover") return false;
      if (selector.includes(":focus-visible") && state !== "focus") return false;
      const normalized = selector.replace(/:hover|:focus-visible/g, "");
      return element.matches(normalized.trim() ? normalized.endsWith(" ") ? `${normalized}*` : normalized : "*");
    });
    if (matches) rule.walkDecls((decl) => {
      if (!important.has(decl.prop) || decl.important) values[decl.prop] = decl.value;
      if (decl.important) important.add(decl.prop);
    });
  });
  return values;
}

function themeBlock(selector: string, endMarker: string): string {
  const start = css.indexOf(selector);
  const end = css.indexOf(endMarker, start);
  return css.slice(start, end);
}

describe("paper workspace visual system", () => {
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
    expect(css).toMatch(/\.brand-mark \.app-logo\s*\{[^}]*filter:\s*none/);
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

  it("keeps all three History panels padded and their card footers usable across screen sizes", () => {
    expect(css).toMatch(/\.history-tabs\s*\{[^}]*flex-wrap:\s*wrap/);
    expect(css).toMatch(/\.history-group-grid\s*\{[^}]*padding:\s*20px 22px/);
    expect(css).toMatch(/\.history-context-badge\s*\{[^}]*border:/);
    expect(css).toMatch(/\.history-group-footer\s*\{[^}]*border-top:[^}]*padding:/);
    expect(css).toMatch(/@media \(max-width:\s*920px\)[\s\S]*?\.history-row\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) auto/);
    expect(css).toMatch(/@media \(max-width:\s*700px\)[\s\S]*?\.history-row\s*\{[^}]*grid-template-columns:\s*1fr/);
    expect(css).toMatch(/@media \(max-width:\s*700px\)[\s\S]*?\.history-group-skill\s*\{[^}]*grid-template-columns:\s*1fr/);
    expect(css).toMatch(/@media \(max-width:\s*700px\)[\s\S]*?\.history-group-footer \.btn\s*\{[^}]*width:\s*100%/);
  });

  it("uses readable contextual label and criterion assessment classes", () => {
    for (const selector of [
      ".authoring-eyebrow",
      ".page-context-kicker",
      ".test-type",
      ".practice-module-kicker",
      ".writing-task-kicker",
      ".writing-review-kicker",
      ".writing-response-kicker",
      ".review-result-label",
      ".history-eyebrow",
      ".history-band-value",
      ".matching-heading-options",
      ".matching-heading-text",
      ".writing-assessment-grid",
      ".writing-criteria-grid",
    ]) {
      expect(css).toContain(selector);
    }
    expect(workspaceValues(`.authoring-eyebrow${workspaceOnly}`)).toMatchObject({ "font-size": "13px", "letter-spacing": ".01em" });
    expect(workspaceValues(`.page-context-kicker${workspaceOnly}`)).toMatchObject({ "font-size": "13px", "letter-spacing": ".01em", "text-transform": "none" });
    expect(css).toMatch(/\.writing-task-kicker[^\{]*\{[^}]*font-size:\s*13px/);
    expect(css).toMatch(/\.review-score \.review-result-label\s*\{[^}]*font-size:\s*13px[^}]*text-transform:\s*none/);
    expect(workspaceValues(`.history-eyebrow${workspaceOnly}`)).toMatchObject({ "font-size": "13px", "letter-spacing": ".01em", "text-transform": "none" });
    expect(css).toMatch(/\.history-band-value\s*\{[^}]*font-size:\s*21px/);
    expect(css).toMatch(/\.matching-heading-options\s*\{[^}]*font-size:\s*15\.5px[^}]*line-height:\s*1\.62/);
    expect(css).toMatch(/\.matching-heading-text\s*\{[^}]*color:\s*var\(--exam-text\)/);
    expect(css).toMatch(/@media \(max-width:\s*520px\)[\s\S]*?\.writing-criteria-grid\s*\{[^}]*grid-template-columns:\s*1fr/);
  });
});

describe("workspace typography and primitive scale", () => {
 it("uses the local Segoe stack and readable body hierarchy", () => {
   expect(workspaceValues("body")).toMatchObject({ "font-family": '"Segoe UI Variable", "Segoe UI", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif', "font-size": "16px", "font-weight": "400", "line-height": "1.6", "letter-spacing": "0" });
   expect(workspaceValues(`.field-help${workspaceOnly}`)).toMatchObject({ "font-size": "13px", "font-weight": "400", "line-height": "1.5" });
   expect(workspaceValues(`.primary-nav-link${workspaceOnly}`)).toMatchObject({ "font-size": "14px", "font-weight": "500", "line-height": "1.4" });
   expect(workspaceValues(`.primary-nav-link-active${workspaceOnly}`)["font-weight"]).toBe("600");
   expect(workspaceValues(`.history-score-state${workspaceOnly}`)["font-weight"]).toBe("600");
   expect(workspaceValues(`.review-score .review-result-label${workspaceOnly}`)["font-weight"]).toBe("500");
 });
 it("uses the approved heading, label and badge scale without changing authored case", () => {
   for (const [selector, size, weight, height, tracking] of [[".page-heading h1", "32px", "600", "1.2", "-.02em"], [".section-title", "22px", "600", "1.3", "-.01em"], [".practice-browser .practice-card-title h3", "18px", "600", "1.35", "-.01em"], [".page-eyebrow", "13px", "500", "1.5", ".01em"], [".field-label", "14px", "500", "1.4", "0"], [".status-badge", "12px", "500", "1.4", "0"], [".module-badge", "12px", "600", "1.4", ".02em"]]) {
     expect(workspaceValues(selector+workspaceOnly), selector).toMatchObject({ "font-size": size, "font-weight": weight, "line-height": height, "letter-spacing": tracking });
   }
   expect(workspaceValues(`.page-heading h1${workspaceOnly}`, "(width < 768px)")["font-size"]).toBe("28px");
   expect(workspaceValues(`.section-title${workspaceOnly}`, "(width < 768px)")["font-size"]).toBe("20px");
   for (const selector of [".page-eyebrow", ".authoring-eyebrow", ".history-eyebrow", ".test-card-title h2"]) expect(workspaceValues(selector+workspaceOnly)["text-transform"]).toBe("none");
   const summary = readFileSync(resolve(process.cwd(), "src/features/test-builder/content-summary.tsx"), "utf8");
   expect(summary).not.toMatch(/uppercase|tracking-wide/);
 });
 it("keeps workspace buttons flat and consistently sized while exam controls stay independent", () => {
   expect(workspaceValues(`.btn${workspaceOnly}`)).toMatchObject({ "font-size": "14px", "font-weight": "600", "line-height": "1.4", "border-radius": "8px", "min-height": "40px", "padding": "0 14px", gap: "8px" });
   expect(workspaceValues(`.btn:hover:not(:disabled)${workspaceOnly}`).transform).toBe("none");
   for (const variant of ["primary", "secondary", "ghost", "danger", "danger-ghost", "listening", "writing"]) expect(workspaceValues(`.btn-${variant}${workspaceOnly}`)["box-shadow"]).toBe("none");
   expect(workspaceValues(`.icon-button${workspaceOnly}`)).toMatchObject({ width: "40px", height: "40px" });
   expect(workspaceValues(".btn")).toMatchObject({ "font-size": "13px", "font-weight": "750", "border-radius": "11px" });
   document.body.innerHTML='<div class="exam-shell"><div class="exam-runner"><button class="btn">Exam</button></div></div>';
   expect(document.querySelector("button")!.matches(`.btn${workspaceOnly}`)).toBe(false);
   document.body.innerHTML="";
 });
 it("uses the approved radius, elevation and spacing rhythm", () => {
   expect(workspaceValues(`.surface-card${workspaceOnly}`)).toMatchObject({ "border-radius": "12px", "box-shadow": "none" });
   expect(workspaceValues(`.field${workspaceOnly}`)["border-radius"]).toBe("8px");
   expect(workspaceValues(`.dialog-panel${workspaceOnly}`)).toMatchObject({ "border-radius": "14px", "box-shadow": "var(--shadow-lg)" });
   expect(workspaceValues(`.page-heading${workspaceOnly}`)["margin-bottom"]).toBe("24px");
   expect(workspaceValues(`.page-eyebrow${workspaceOnly}`).margin).toBe("0 0 8px");
   expect(workspaceValues(`.page-description${workspaceOnly}`).margin).toBe("12px 0 0");
   for (const selector of [".profile-form", ".profile-grid", ".auth-form"]) expect(workspaceValues(selector+workspaceOnly).gap).toBe("16px");
   expect(workspaceValues(`.profile-card${workspaceOnly}`).gap).toBe("24px");
   expect(workspaceValues(".practice-browser .practice-grid").gap).toBe("16px");
 });
});

it("removes decorative workspace gradients, blur and colored elevation while preserving functional visuals", () => {
  for (const selector of ["body", ".app-header", ".home-hero", ".home-orbit-glow", ".home-orbit-core::before", ".empty-state", ".history-group-heading", ".passage-card-header", ".listening-builder, .listening-empty", ".writing-builder"]) {
    const escaped=selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const block=css.match(new RegExp(escaped+"\\s*\\{([^}]+)"))?.[1];
    expect(block,selector).toBeDefined();
    expect(block,selector).not.toMatch(/gradient|backdrop-filter:\s*blur|drop-shadow/);
  }
  expect(css).not.toContain(".app-shell::before");
  expect(css).not.toContain(".home-hero::after");
  expect(css).toContain(".home-orbit-interactive.is-active .home-orbit-scene");
  expect(css).toContain(".trend-chart");
  expect(css).toContain(".highlight-mark");
});

describe("final workspace hover focus and reduced-motion contracts", () => {
  it.each(["light", "dark"])("keeps every current button variant flat with visible focus in %s", (theme) => {
    document.documentElement.dataset.theme = theme;
    const surface = document.createElement("div");
    document.body.append(surface);
    for (const variant of ["primary", "secondary", "ghost", "danger", "danger-ghost", "listening", "writing"]) {
      const button = document.createElement("button"); button.className = `btn btn-${variant}`; surface.append(button);
      const hover = interactionValues(button, "hover");
      expect(hover.transform, variant).toBe("none");
      expect(["none", "var(--shadow-sm)"]).toContain(hover["box-shadow"]);
      expect(hover.background ?? "", variant).not.toMatch(/gradient|glow/);
      const focus = interactionValues(button, "focus");
      expect(focus.outline).toMatch(/^3px solid /); expect(focus["outline-color"]).toBe("var(--accent)"); expect(focus["outline-offset"]).toBe("3px");
      expect(interactionValues(button, "reduced")["transition-duration"]).toBe("0.01ms");
    }
    surface.remove(); document.documentElement.dataset.theme = "light";
  });

  it("retains neutral card hover, readable fields, badges and status presentation", () => {
    const surface = document.createElement("div"); document.body.append(surface);
    for (const className of ["home-metric", "learning-path-card", "practice-card", "test-card"]) {
      const card = document.createElement("a"); card.className = className; surface.append(card);
      const hover = interactionValues(card, "hover"); expect(hover.transform).toBe("none"); expect(["none", "var(--shadow-sm)"]).toContain(hover["box-shadow"]); expect(hover.background ?? "").not.toMatch(/gradient|glow/);
    }
    for (const className of ["field", "select-field", "textarea-field"]) {
      const input = document.createElement("input"); input.className = className; surface.append(input);
      expect(interactionValues(input, "focus")["outline-color"]).toBe("var(--accent)"); expect(["var(--accent)", "var(--line-strong)"]).toContain(interactionValues(input, "hover")["border-color"]);
    }
    for (const skill of ["reading", "listening", "writing"]) {
      const badge = document.createElement("span"); badge.className = `module-badge module-${skill}`; surface.append(badge);
      expect(interactionValues(badge, "hover")).toMatchObject({ color: `var(--${skill})`, background: `color-mix(in srgb, var(--${skill}) 8%, var(--surface))` });
    }
    for (const state of ["published", "draft", "archived"]) {
      const badge = document.createElement("span"); badge.className = `status-badge status-${state}`; surface.append(badge);
      const values = interactionValues(badge, "hover"); expect(values["font-size"]).toBe("12px"); expect(values.background).not.toMatch(/gradient|glow/);
    }
    surface.remove();
  });

  it("keeps global navigation focus and active markers visible and normal chrome unblurred", () => {
    expect(workspaceValues(".primary-nav-link-active")).toMatchObject({ "border-bottom-color": "var(--accent)", background: "var(--surface-raised)" });
    const nav = document.createElement("a"); nav.className = "primary-nav-link"; document.body.append(nav);
    expect(interactionValues(nav, "focus")).toMatchObject({ "outline-color": "var(--accent)", "outline-offset": "3px" }); nav.remove();
    for (const selector of [".app-header", ".dialog-backdrop", ".app-footer"]) expect(workspaceValues(selector)["backdrop-filter"] ?? "none").toBe("none");
    for (const selector of [".header-actions a", ".header-actions button"]) {
      expect(workspaceValues(selector, "(width < 768px)")["min-height"]).toBe("44px");
    }
    expect(workspaceValues(".primary-nav-link")["min-height"]).toBe("44px");
  });
});
