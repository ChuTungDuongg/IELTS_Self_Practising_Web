import { act, fireEvent, screen, within } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppFooter } from "@/components/ui/app-footer";
import { LocaleProvider } from "@/lib/i18n/locale-provider";
import { renderWithLocale } from "./locale-test-utils";

beforeEach(() => window.localStorage.clear());

describe("shared footer", () => {
  it("shows real product information and the current language without extra links or controls", () => {
    renderWithLocale(<AppFooter year={2026} />);
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent("IELTS Studio");
    expect(footer).toHaveTextContent("Practice & authoring");
    expect(footer).toHaveTextContent("© 2026 IELTS Studio");
    expect(within(footer).getByText("English")).toHaveAttribute("lang", "en");
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    expect(screen.getByRole("contentinfo")).toBe(footer);
    expect(footer).toHaveTextContent("Luyện tập và biên soạn đề");
    expect(within(footer).getByText("Tiếng Việt")).toHaveAttribute("lang", "vi");
    expect(footer.querySelector("a, button, select")).toBeNull();
  });

  it("uses the server year consistently through English hydration and Vietnamese restoration", async () => {
    window.localStorage.setItem("ielts-locale", "vi");
    const tree = <LocaleProvider><AppFooter year={2026} /></LocaleProvider>;
    const markup = renderToString(tree);
    expect(markup).toContain("© 2026 IELTS Studio");
    expect(markup).toContain("Practice &amp; authoring");
    expect(markup).toContain("English");
    const container = document.createElement("div");
    container.innerHTML = markup;
    document.body.append(container);
    const recoverable = vi.fn();
    let root: ReturnType<typeof hydrateRoot>;
    await act(async () => { root = hydrateRoot(container, tree, { onRecoverableError: recoverable }); });
    expect(container).toHaveTextContent("© 2026 IELTS Studio");
    expect(container).toHaveTextContent("Luyện tập và biên soạn đề");
    expect(recoverable).not.toHaveBeenCalled();
    await act(async () => root!.unmount());
    container.remove();
  });

  it("keeps the footer in normal flow below a growing main", () => {
    const css = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));
    function values(selector: string) {
      const result: Record<string, string> = {};
      css.nodes.forEach((node) => { if (node.type === "rule" && node.selector === selector) node.walkDecls((decl) => { result[decl.prop] = decl.value; }); });
      return result;
    }
    expect(values(".app-shell")).toMatchObject({ display: "flex", "flex-direction": "column", "min-height": "100dvh" });
    expect(values(".app-content").flex).toBe("1");
    expect(values(".app-footer").display).toBe("flex");
    expect(["fixed", "absolute"]).not.toContain(values(".app-footer").position);
  });
});
