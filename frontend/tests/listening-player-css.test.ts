import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const stylesheet = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));
function declarations(selector: string, media?: string) {
  const result: Record<string, string> = {};
  stylesheet.walkRules((rule) => {
    const query = rule.parent?.type === "atrule" ? rule.parent.params : undefined;
    if (rule.selector === selector && query === media) rule.walkDecls((decl) => { result[decl.prop] = decl.value; });
  });
  return result;
}

it("reserves separate desktop content, right rail and bottom audio regions without an overlay", () => {
  expect(declarations(".exam-runner.listening-attempt")).toMatchObject({ height: "100dvh", "min-height": "0" });
  expect(declarations(".listening-attempt-body")).toMatchObject({ display: "grid", "grid-template-columns": "minmax(0, 1fr) 228px", flex: "1", "min-height": "0", "min-width": "0" });
  expect(declarations(".listening-attempt-body > .listening-question-pane")).toMatchObject({ "min-width": "0", "min-height": "0", "max-height": "none", "overflow-y": "auto" });
  expect(declarations(".listening-navigation-rail")).toMatchObject({ display: "flex", "flex-direction": "column", "min-width": "0", "min-height": "0", "border-left": "1px solid var(--exam-border)" });
  expect(declarations(".listening-navigation-scroll")).toMatchObject({ flex: "1", "min-height": "0", "overflow-y": "auto" });
  expect(declarations(".listening-navigation-actions").flex).toBe("0 0 auto");
  expect(declarations(".listening-question-navigation .listening-section-questions")).toMatchObject({ display: "grid", "grid-template-columns": "repeat(3, minmax(0, 1fr))" });
  expect(declarations(".listening-audio-dock")).toMatchObject({ flex: "0 0 auto", "min-width": "0", position: "static" });
  const source = readFileSync(resolve(process.cwd(), "src/features/listening/listening-runner.tsx"), "utf8");
  expect(source).not.toMatch(/exam-footer|exam-question-strip|listening-lower-dock/);
  expect(source.indexOf('className="listening-attempt-body"')).toBeLessThan(source.indexOf('className="listening-audio-dock"'));
  expect(source).not.toMatch(/innerWidth|matchMedia/);
});

it("uses a full-width progress row and independently centered transport with three control groups", () => {
  expect(declarations(".listening-player-exam-bar .player-progress-row").width).toBe("100%");
  expect(declarations('.listening-player-exam-bar .player-progress-row input').width).toBe("100%");
  expect(declarations(".listening-player-exam-bar .player-control-row")).toMatchObject({ display: "grid", "grid-template-columns": "minmax(0, 1fr) auto minmax(0, 1fr)" });
  expect(declarations(".listening-player-exam-bar .player-transport")["justify-self"]).toBe("center");
  expect(declarations(".listening-player-exam-bar .player-speed-control")["justify-self"]).toBe("end");
  expect(declarations(".listening-player-exam-bar .player-main")).toMatchObject({ width: "44px", height: "44px", "border-radius": "50%", "box-shadow": "none" });
  expect(declarations(".listening-player-exam-bar").padding).toBe("4px 16px");
  expect(declarations(".listening-player-exam-bar .player-progress-row input")).toMatchObject({ display: "block", "min-height": "24px" });
  expect(declarations(".listening-player-exam-bar .player-left-controls")).toMatchObject({ display: "flex", "align-items": "center" });
});

it("narrows the tablet rail and stacks it only on small screens with CSS", () => {
  expect(declarations(".listening-attempt-body", "(max-width: 900px)")["grid-template-columns"]).toBe("minmax(0, 1fr) 196px");
  expect(declarations(".listening-attempt-body", "(max-width: 640px)")).toMatchObject({ "grid-template-columns": "minmax(0, 1fr)", "grid-template-rows": "minmax(0, 1fr) auto", overflow: "auto" });
  expect(declarations(".listening-navigation-rail", "(max-width: 640px)")).toMatchObject({ "max-height": "32dvh", "border-left": "0", "border-top": "1px solid var(--exam-border)" });
  expect(declarations(".listening-player-exam-bar .player-control-row", "(max-width: 640px)")).toMatchObject({ display: "flex", "flex-wrap": "wrap" });
  expect(declarations(".listening-player-exam-bar .player-time").display).toBe("block");
  expect(declarations('.listening-player-exam-bar .player-volume-controls input[type="range"]').display).toBe("block");
  expect(declarations(".listening-player-exam-bar .player-transport .player-skip")).toMatchObject({ display: "grid", "min-height": "44px" });
});

it("keeps sequential navigation compact and secondary inside the rail action area", () => {
  expect(declarations(".listening-sequential-navigation")).toMatchObject({ display: "flex", "justify-content": "center", gap: "8px" });
  expect(declarations(".listening-sequential-navigation button")).toMatchObject({ display: "grid", width: "40px", "min-height": "36px", "place-items": "center", color: "var(--exam-muted)", background: "var(--exam-control-bg)" });
  expect(declarations(".listening-previous-icon").transform).toBe("rotate(180deg)");
  expect(declarations(".listening-sequential-navigation button:disabled").opacity).toBe(".45");
});

it("isolates dock geometry and exam surfaces while the selected section uses the personal accent", () => {
  const rules: string[] = [];
  const examPaletteRules: string[] = [];
  stylesheet.walkRules((rule) => {
    if (/listening-(audio-dock|navigation|sequential-navigation|previous-icon|section-navigation|question-navigation|player-exam-bar|attempt)/.test(rule.selector)) {
      rules.push(rule.toString());
      // Personalization deliberately colors this selected control. Keep the
      // surrounding panels/player on exam tokens and retain all geometry checks.
      if (rule.selector !== ".listening-section-navigation button.active") examPaletteRules.push(rule.toString());
    }
  });
  const scoped = rules.join("\n");
  expect(rules.length).toBeGreaterThan(8);
  expect(scoped).toContain("var(--exam-surface)"); expect(scoped).toContain("var(--exam-accent)");
  expect(scoped).not.toMatch(/position:\s*(fixed|absolute)|overflow(?:-x)?:\s*(hidden|clip)|gradient\(/);
  expect(examPaletteRules.join("\n")).not.toMatch(/var\(--(?:accent|surface|listening|glow)[\w-]*\)/);
  expect(declarations(".listening-section-navigation button.active")).toMatchObject({ "border-color": "var(--accent)", color: "var(--accent-contrast)", background: "var(--accent)" });
  const source = readFileSync(resolve(process.cwd(), "src/features/listening/audio-player.tsx"), "utf8");
  expect(source).not.toMatch(/window\.innerWidth|usePathname|matchMedia/);
});
