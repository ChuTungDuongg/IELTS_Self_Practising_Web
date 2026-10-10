import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { expect, it } from "vitest";

const stylesheet = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));
function declarations(selector: string) {
  const result: Record<string, string> = {};
  stylesheet.walkRules((rule) => { if (rule.selector === selector && rule.parent?.type === "root") rule.walkDecls((decl) => { result[decl.prop] = decl.value; }); });
  return result;
}

it("reserves the Listening bottom stack in a viewport flex layout without overlaying the scrollable pane", () => {
  expect(declarations(".exam-runner.listening-attempt")).toMatchObject({ height: "100dvh", "min-height": "0" });
  expect(declarations(".listening-lower-dock")).toMatchObject({ flex: "0 0 auto", "min-width": "0" });
  expect(declarations(".listening-attempt > .listening-question-pane")).toMatchObject({ "min-height": "0", "max-height": "none" });
  expect(declarations(".listening-lower-dock > .listening-exam-footer").position).toBe("static");
});

it("uses a full-width progress row and independently centered transport with three control groups", () => {
  expect(declarations(".listening-player-exam-bar .player-progress-row").width).toBe("100%");
  expect(declarations('.listening-player-exam-bar .player-progress-row input').width).toBe("100%");
  expect(declarations(".listening-player-exam-bar .player-control-row")).toMatchObject({ display: "grid", "grid-template-columns": "minmax(0, 1fr) auto minmax(0, 1fr)" });
  expect(declarations(".listening-player-exam-bar .player-transport")["justify-self"]).toBe("center");
  expect(declarations(".listening-player-exam-bar .player-speed-control")["justify-self"]).toBe("end");
  expect(declarations(".listening-player-exam-bar .player-main")).toMatchObject({ width: "56px", height: "56px", "border-radius": "50%", "box-shadow": "none" });
});

it("wraps controls with CSS and keeps controls visible at narrow widths", () => {
  const wraps: Record<string, string> = {};
  stylesheet.walkAtRules("media", (media) => {
    if (media.params !== "(max-width: 760px)") return;
    media.walkRules((rule) => { if (rule.selector === ".listening-player-exam-bar .player-control-row") rule.walkDecls((decl) => { wraps[decl.prop] = decl.value; }); });
  });
  expect(wraps).toMatchObject({ display: "flex", "flex-wrap": "wrap" });
  expect(declarations(".listening-player-exam-bar .player-time").display).toBe("block");
  expect(declarations('.listening-player-exam-bar .player-volume-controls input[type="range"]').display).toBe("block");
  expect(declarations(".listening-player-exam-bar .player-transport .player-skip")).toMatchObject({ display: "grid", "min-height": "44px" });
});

it("scopes the dock to exam tokens without fixed positioning, clipping, gradients or workspace accents", () => {
  const rules: string[] = [];
  stylesheet.walkRules((rule) => {
    if (/listening-(audio-dock|lower-dock|player-exam-bar|attempt)/.test(rule.selector)) rules.push(rule.toString());
  });
  const scoped = rules.join("\n");
  expect(rules.length).toBeGreaterThan(8);
  expect(scoped).toContain("var(--exam-surface)"); expect(scoped).toContain("var(--exam-accent)");
  expect(scoped).not.toMatch(/position:\s*(fixed|absolute)|overflow(?:-x)?:\s*(hidden|clip)|gradient\(|var\(--(?:accent|surface|listening|glow)[\w-]*\)/);
  const source = readFileSync(resolve(process.cwd(), "src/features/listening/audio-player.tsx"), "utf8");
  expect(source).not.toMatch(/window\.innerWidth|usePathname|matchMedia/);
});
