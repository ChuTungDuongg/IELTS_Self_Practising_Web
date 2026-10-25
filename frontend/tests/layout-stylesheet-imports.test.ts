// @vitest-environment node
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const layoutPath = resolve("src/app/layout.tsx");
const request = createRequire(layoutPath);
const imports = [...readFileSync(layoutPath, "utf8").matchAll(/^import ["']([^"']+)["'];/gm)].map(match => match[1]);

describe("root stylesheet resolution", () => {
  it("resolves every side-effect stylesheet import through its package exports", () => {
    expect(imports.length).toBeGreaterThan(0);
    for (const specifier of imports) expect(() => request.resolve(specifier), specifier).not.toThrow();
  });
  it("ships the local font files referenced by every imported font stylesheet", () => {
    const fonts = imports.filter(specifier => specifier.startsWith("@fontsource"));
    expect(fonts.length).toBeGreaterThan(0);
    for (const specifier of fonts) {
      const stylesheet = request.resolve(specifier);
      const css = readFileSync(stylesheet, "utf8");
      expect(css).toContain("font-display: swap");
      for (const [, url] of css.matchAll(/url\(["']?([^\s)"']+)["']?\)/g)) {
        expect(readFileSync(resolve(dirname(stylesheet), url)).length).toBeGreaterThan(0);
      }
    }
  });
});
