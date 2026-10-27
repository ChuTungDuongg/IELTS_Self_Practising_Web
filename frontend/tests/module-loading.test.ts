import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import ts from "typescript";
import { expect, it } from "vitest";

// Follow only static runtime imports/re-exports; import() is a loading boundary.
function eagerModules(entry: string): Set<string> {
  const seen = new Set<string>();
  function visit(file: string) {
    if (seen.has(file)) return;
    seen.add(file);
    const tree = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);
    for (const node of tree.statements) {
      if (!ts.isImportDeclaration(node) && !ts.isExportDeclaration(node)) continue;
      if (ts.isExportDeclaration(node) && node.isTypeOnly) continue;
      if (ts.isImportDeclaration(node) && node.importClause?.isTypeOnly) continue;
      const specifier = node.moduleSpecifier;
      if (!specifier || !ts.isStringLiteral(specifier)) continue;
      const name = specifier.text;
      const base = name.startsWith("@/") ? resolve("src", name.slice(2)) : name.startsWith(".") ? resolve(dirname(file), name) : null;
      if (!base) continue;
      const target = [base + ".ts", base + ".tsx", resolve(base, "index.ts"), resolve(base, "index.tsx")].find(existsSync);
      if (target) visit(target);
    }
  }
  visit(resolve(entry));
  return seen;
}

it("loads advanced Classroom panels only when their tabs are selected", () => {
  const graph = eagerModules("src/features/classrooms/content/classroom-workspace.tsx");
  for (const panel of ["gradebook", "learning-analytics", "learning-plans", "student-profile"])
    expect(graph.has(resolve(`src/features/classrooms/lms/${panel}.tsx`)), panel).toBe(false);
});

it("keeps the homepage WebGL scene outside the global shell import graph", () => {
  const graph = eagerModules("src/components/ui/app-shell.tsx");
  expect([...graph].some(file => /gravity[/\\]scene\./.test(file))).toBe(false);
});
