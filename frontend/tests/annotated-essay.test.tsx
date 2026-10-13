import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnnotatedEssay } from "@/features/writing/annotated-essay";
import type { WritingAnnotation } from "@/lib/api/writing-ai";

const issue: WritingAnnotation = {
  id: "grammar-1", criterion: "gra", kind: "ERROR", source_id: "P1S1",
  start_offset: 0, end_offset: 12, original_span: "people tends",
  suggested_revision: "people tend", message: "Use a plural verb.", confidence: "HIGH", category: "grammar",
};

describe("AnnotatedEssay", () => {
  it("keeps the exact saved text including CRLF, spacing and emoji", () => {
    const content = "  😀\r\n\r\npeople tends to help.\r\n";
    const { container } = render(<AnnotatedEssay content={content} annotations={[{ ...issue, start_offset: 8, end_offset: 20 }]} />);
    expect(container.querySelector("[data-essay-text]")?.textContent).toBe(content);
    expect(screen.getByRole("button", { name: /people tends/ })).toHaveTextContent("people tends");
    expect(container.querySelector("[data-essay-text] button")).toBeNull();
  });

  it("renders plain essays without decoration", () => {
    const { container } = render(<AnnotatedEssay content="Plain <script>essay</script>." annotations={[]} />);
    expect(container.querySelector("[data-essay-text]")?.textContent).toBe("Plain <script>essay</script>.");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  it.each(["hover", "focus", "tap", "keyboard"])("opens safe revision feedback with %s and closes with Escape", (method) => {
    render(<AnnotatedEssay content="people tends to help." annotations={[issue]} />);
    const span = screen.getByRole("button", { name: /people tends/ });
    if (method === "hover") fireEvent.mouseEnter(span);
    if (method === "focus") fireEvent.focus(span);
    if (method === "tap") fireEvent.click(span);
    if (method === "keyboard") fireEvent.keyDown(span, { key: "Enter" });
    const popover = screen.getByRole("dialog", { name: /suggestion/i });
    expect(within(popover).getByText("GRA · Grammar")).toBeInTheDocument();
    expect(within(popover).getByText("people tend")).toBeInTheDocument();
    expect(popover).toHaveTextContent("Suggested revision");
    expect(popover).toHaveTextContent("Use a plural verb.");
    expect(span).toHaveAccessibleDescription(/Use a plural verb/);
    expect(popover).not.toHaveTextContent("P1S1");
    fireEvent.keyDown(span, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps a tapped popover pinned after the pointer leaves and allows closing", () => {
    render(<AnnotatedEssay content="people tends to help." annotations={[issue]} />);
    const span = screen.getByRole("button", { name: /people tends/ });
    fireEvent.click(span); fireEvent.mouseLeave(span);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close suggestions" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps a pinned suggestion while hovering another issue", () => {
    render(<AnnotatedEssay content="people tends goverment" annotations={[issue,
      { ...issue, id: "spelling", criterion: "lr", category: "spelling", start_offset: 13, end_offset: 22, original_span: "goverment", message: "Correct the spelling." },
    ]} />);
    fireEvent.click(screen.getByRole("button", { name: /people tends/ }));
    fireEvent.mouseEnter(screen.getByRole("button", { name: /goverment/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Use a plural verb.");
    expect(screen.getByRole("dialog")).not.toHaveTextContent("Correct the spelling.");
  });

  it("opens newly split overlap segments after a pinned interval is replaced", () => {
    const lexical = { ...issue, id: "lexical", criterion: "lr" as const, kind: "OPTIONAL_REFINEMENT" as const, start_offset: 7, original_span: "tends", suggested_revision: "supports", message: "A contextual refinement." };
    const view = render(<AnnotatedEssay content="people tends to help." annotations={[issue]} />);
    fireEvent.click(screen.getByRole("button", { name: /people tends/ }));
    view.rerender(<AnnotatedEssay content="people tends to help." annotations={[issue, lexical]} />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: /2 suggestions.*tends/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent("A contextual refinement.");
    expect(screen.getByRole("dialog")).toHaveTextContent("Use a plural verb.");
  });

  it("uses softer optional styling and LR spelling ownership", () => {
    render(<AnnotatedEssay content="people tends goverment" annotations={[
      { ...issue, kind: "OPTIONAL_REFINEMENT" },
      { ...issue, id: "spelling", criterion: "lr", category: "spelling", start_offset: 13, end_offset: 22, original_span: "goverment", suggested_revision: "government" },
    ]} />);
    expect(screen.getByRole("button", { name: /people tends/ })).toHaveAttribute("data-severity", "OPTIONAL_REFINEMENT");
    fireEvent.focus(screen.getByRole("button", { name: /goverment/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent("LR · Spelling");
  });

  it("splits overlapping intervals once and exposes both suggestions", () => {
    const lexical = { ...issue, id: "lexical", criterion: "lr" as const, start_offset: 7, original_span: "tends", suggested_revision: "supports", kind: "OPTIONAL_REFINEMENT" as const };
    const { container } = render(<AnnotatedEssay content="people tends to help." annotations={[lexical, issue, issue]} />);
    expect(container.querySelector("[data-essay-text]")?.textContent).toBe("people tends to help.");
    const overlap = screen.getByRole("button", { name: /2 suggestions.*tends/ });
    expect(overlap).toHaveAttribute("data-severity", "ERROR");
    expect(overlap.querySelector('[role="button"]')).toBeNull();
    fireEvent.focus(overlap);
    expect(screen.getByRole("dialog")).toHaveTextContent("people tend");
    expect(screen.getByRole("dialog")).toHaveTextContent("supports");
  });

  it("ignores mismatched, invalid, out-of-range, TA/CC and medium error annotations", () => {
    render(<AnnotatedEssay content="people tends to help." annotations={[
      { ...issue, end_offset: 200 }, { ...issue, id: "bad", start_offset: -1 },
      { ...issue, id: "mismatch", original_span: "other" },
      { ...issue, id: "empty", end_offset: 0 }, { ...issue, id: "fraction", start_offset: 0.5 },
      { ...issue, id: "ta", criterion: "ta" }, { ...issue, id: "cc", criterion: "cc" },
      { ...issue, id: "uncertain", confidence: "MEDIUM" },
    ]} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each(["light", "dark"])("keeps semantic severity and focus presentation in the %s theme", theme => {
    const { container } = render(<div data-theme={theme}><AnnotatedEssay content="people tends" annotations={[issue]} /></div>);
    const span = screen.getByRole("button", { name: /people tends/ });
    expect(span).toHaveAttribute("data-severity", "ERROR");
    expect(span.className).toMatch(/annotation/);
    expect(span).not.toHaveAttribute("style");
    fireEvent.focus(span);
    expect(container.querySelector('[role="dialog"]')).toBeInTheDocument();
  });
});
