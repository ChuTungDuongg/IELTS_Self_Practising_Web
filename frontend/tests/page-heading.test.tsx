import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import postcss from "postcss";
import { beforeEach, describe, expect, it } from "vitest";
import { PageHeading } from "@/components/ui/page-heading";
import { UiText } from "@/lib/i18n/locale-provider";
import type { TranslationKey } from "@/lib/i18n/types";
import { renderWithLocale } from "./locale-test-utils";

const css = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));

// Inspect the heading's source CSS contract without claiming browser layout coverage.
function headingStyles(element: Element) {
  const values: Record<string, string> = {};
  css.walkRules((rule) => {
    if (rule.parent?.type === "atrule") return;
    if (!postcss.list.comma(rule.selector).some((selector) => !selector.includes(":hover") && !selector.includes(":focus") && !selector.includes("::") && element.matches(selector))) return;
    rule.walkDecls((declaration) => { values[declaration.prop] = declaration.value; });
  });
  return values;
}

const contexts: [TranslationKey, string, string, string?][] = [
  ["pages.library.practice", "Practice", "Luyện tập"],
  ["pages.practice", "Practice", "Luyện tập"],
  ["pages.progress", "Progress", "Tiến độ"],
  ["admin.administration", "Administration", "Quản trị"],
  ["transfer.portability", "Local portability", "Chuyển dữ liệu cục bộ"],
  ["pages.record", "Practice record", "Nhật ký luyện tập", "history-eyebrow"],
  ["profile.profile", "Profile", "Hồ sơ"],
  ["builder.workspace", "Authoring workspace", "Không gian biên soạn", "authoring-eyebrow"],
];

describe("page heading context labels", () => {
  beforeEach(() => { localStorage.clear(); document.documentElement.dataset.theme = "light"; });

  it.each(contexts)("preserves %s text and locale changes with the shared reference style", (message, english, vietnamese, eyebrowClassName) => {
    renderWithLocale(<PageHeading eyebrow={<UiText message={message} />} eyebrowClassName={eyebrowClassName} title="Page title" description="Page description" />);
    const label = screen.getByText(english);
    expect(headingStyles(label)).toMatchObject({
      display: "inline-flex", color: "var(--accent)", "border-left": "3px solid var(--accent)",
      background: "color-mix(in srgb, var(--accent) 8%, transparent)", padding: "3px 9px",
      "font-size": "13px", "font-weight": "500", "line-height": "1.5",
      "letter-spacing": ".01em", "text-transform": "none", margin: "0 0 8px",
    });
    const title = screen.getByRole("heading", { level: 1, name: "Page title" });
    expect(label.nextElementSibling).toBe(title);
    expect(headingStyles(title)).toMatchObject({ margin: "0", "font-size": "32px", "line-height": "1.2" });
    expect(headingStyles(screen.getByText("Page description"))).toMatchObject({ margin: "12px 0 0" });
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByText(vietnamese)).toBe(label);
    expect(title).toHaveTextContent("Page title");
  });

  it("keeps headings without a context label and heading actions intact", () => {
    const { container } = render(<PageHeading title="Untitled test" action={<button type="button">Open</button>} />);
    expect(container.querySelector(".page-context-kicker")).toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Untitled test");
    expect(screen.getByRole("button", { name: "Open" })).toBeInTheDocument();
  });
});
