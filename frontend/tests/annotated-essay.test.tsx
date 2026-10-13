import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnnotatedEssay } from "@/features/writing/annotated-essay";
import type { WritingAnnotation } from "@/lib/api/writing-ai";

const issue: WritingAnnotation = {
  id: "grammar-1", criterion: "gra", kind: "ERROR", source_id: "P1S1",
  start_offset: 0, end_offset: 12, original_span: "people tends",
  suggested_revision: "people tend", message: "Use a plural verb.", confidence: "HIGH", category: "grammar",
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

function mockLayout({ x = 200, y = 100, width = 100, height = 20, panelHeight = 200, viewportWidth = 1000, viewportHeight = 800 } = {}) {
  vi.stubGlobal("innerWidth", viewportWidth);
  vi.stubGlobal("innerHeight", viewportHeight);
  const anchor = { x, y, width, height };
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const rect = this.getAttribute("role") === "dialog"
      ? { x: 0, y: 0, width: 360, height: panelHeight } : anchor;
    return { ...rect, left: rect.x, top: rect.y, right: rect.x + rect.width, bottom: rect.y + rect.height, toJSON: () => rect };
  });
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(panelHeight);
  return anchor;
}

function openMeasuredEssay() {
  const view = render(<AnnotatedEssay content="people tends to help." annotations={[issue]} />);
  fireEvent.mouseEnter(screen.getByRole("button", { name: /people tends/ }));
  return { ...view, panel: screen.getByRole("dialog") };
}

describe("AnnotatedEssay", () => {
  it("renders plain essays as three separate paragraph blocks", () => {
    const content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.";
    const { container } = render(<AnnotatedEssay content={content} />);
    const essay = container.querySelector("[data-essay-text]")!;
    expect([...essay.querySelectorAll("p")].map(paragraph => paragraph.textContent))
      .toEqual(["First paragraph.", "Second paragraph.", "Third paragraph."]);
    expect(essay.textContent).toBe(content);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each(["\n", "\r\n", "\r"])("treats a single %j newline as a paragraph separator", separator => {
    const content = `First paragraph.${separator}Second paragraph.`;
    const { container } = render(<AnnotatedEssay content={content} />);
    const essay = container.querySelector("[data-essay-text]")!;
    expect(essay.querySelectorAll("p")).toHaveLength(2);
    expect(essay.querySelector("[hidden]")?.textContent).toBe(separator);
    expect(essay.textContent).toBe(content);
  });

  it("collapses the visual space of a long mixed newline run without changing its text", () => {
    const separator = "\n\n\r\n\r\n\r\r\n";
    const content = `First paragraph.${separator}Second paragraph.`;
    const { container } = render(<AnnotatedEssay content={content} annotations={[]} />);
    const essay = container.querySelector("[data-essay-text]")!;
    expect([...essay.querySelectorAll("p")].map(paragraph => paragraph.textContent))
      .toEqual(["First paragraph.", "Second paragraph."]);
    const separators = essay.querySelectorAll("[hidden]");
    expect(separators).toHaveLength(1);
    expect(separators[0]).toHaveTextContent("");
    expect(separators[0].textContent).toBe(separator);
    expect(separators[0]).not.toBeVisible();
    expect(essay.textContent).toBe(content);
  });

  it("preserves edge separators, spaces and UTF-16 offsets for GRA in paragraph two and LR in paragraph three", () => {
    const leading = "\r\n\n";
    const first = "  😀 people tends.";
    const second = "people tends in paragraph two.  ";
    const third = "A goverment decision. ";
    const beforeSecond = `${leading}${first}\r\n\r\n`;
    const beforeThird = `${beforeSecond}${second}\n\n`;
    const content = `${beforeThird}${third}\r\r\n`;
    const grammar = { ...issue, start_offset: beforeSecond.length, end_offset: beforeSecond.length + 12 };
    const spelling: WritingAnnotation = {
      ...issue, id: "spelling", criterion: "lr", category: "spelling", original_span: "goverment",
      start_offset: beforeThird.length + 2, end_offset: beforeThird.length + 11,
      suggested_revision: "government", message: "Correct the spelling.",
    };
    const { container } = render(<AnnotatedEssay content={content} annotations={[grammar, spelling]} />);
    const essay = container.querySelector("[data-essay-text]")!;
    const paragraphs = essay.querySelectorAll("p");
    expect([...paragraphs].map(paragraph => paragraph.textContent)).toEqual([first, second, third]);
    expect(paragraphs[0].querySelector('[role="button"]')).toBeNull();
    const gra = within(paragraphs[1]).getByRole("button", { name: /people tends/ });
    expect(gra.textContent).toBe(content.slice(grammar.start_offset, grammar.end_offset));
    expect(gra).toHaveAttribute("data-annotation-ids", issue.id);
    fireEvent.focus(gra);
    expect(screen.getByRole("dialog")).toHaveTextContent("GRA · Grammar");
    const lr = within(paragraphs[2]).getByRole("button", { name: /goverment/ });
    expect(lr.textContent).toBe(content.slice(spelling.start_offset, spelling.end_offset));
    fireEvent.focus(lr);
    expect(screen.getByRole("dialog")).toHaveTextContent("LR · Spelling");
    expect(screen.getByRole("dialog")).toHaveTextContent("government");
    expect(essay.textContent).toBe(content);
    expect(essay.firstElementChild).toHaveAttribute("hidden");
    expect(essay.lastElementChild).toHaveAttribute("hidden");
  });

  it("keeps newline-only content without empty visual paragraphs", () => {
    const content = "\n\r\n\r";
    const { container } = render(<AnnotatedEssay content={content} />);
    const essay = container.querySelector("[data-essay-text]")!;
    expect(essay.querySelectorAll("p")).toHaveLength(0);
    expect(essay.textContent).toBe(content);
    expect(essay.firstElementChild).not.toBeVisible();
  });

  it("splits a cross-paragraph annotation into safe fragments with the same identity", () => {
    const content = "people tends\r\n\r\npeople agree.";
    const cross: WritingAnnotation = { ...issue, start_offset: 7, end_offset: 22, original_span: "tends\r\n\r\npeople" };
    const { container } = render(<AnnotatedEssay content={content} annotations={[cross]} />);
    const essay = container.querySelector("[data-essay-text]")!;
    const fragments = essay.querySelectorAll('[data-annotation-ids="grammar-1"]');
    expect([...fragments].map(fragment => fragment.textContent)).toEqual(["tends", "people"]);
    expect(essay.querySelectorAll("p")).toHaveLength(2);
    expect(essay.querySelector("[hidden] [role=button]")).toBeNull();
    for (const fragment of fragments) {
      expect(fragment.querySelector('[role="button"]')).toBeNull();
      fireEvent.focus(fragment);
      expect(screen.getByRole("dialog").querySelector("p")?.textContent).toBe(cross.original_span);
    }
    expect(essay.textContent).toBe(content);
  });

  it("retains overlapping GRA and LR spans inside a later paragraph", () => {
    const prefix = "😀 First paragraph.\r\n\r\n";
    const content = `${prefix}people tends to help.`;
    const grammar = { ...issue, start_offset: prefix.length, end_offset: prefix.length + 12 };
    const lexical: WritingAnnotation = { ...grammar, id: "lexical", criterion: "lr", start_offset: prefix.length + 7, original_span: "tends", suggested_revision: "supports", kind: "OPTIONAL_REFINEMENT" };
    const { container } = render(<AnnotatedEssay content={content} annotations={[grammar, lexical]} />);
    const essay = container.querySelector("[data-essay-text]")!;
    const overlap = within(essay.querySelectorAll("p")[1]).getByRole("button", { name: /2 suggestions.*tends/ });
    expect(overlap).toHaveAttribute("data-annotation-ids", "grammar-1 lexical");
    fireEvent.focus(overlap);
    expect(screen.getByRole("dialog")).toHaveTextContent("people tend");
    expect(screen.getByRole("dialog")).toHaveTextContent("supports");
    expect(essay.textContent).toBe(content);
  });

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
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(screen.getByRole("dialog").parentElement).toBe(document.body);
  });

  it("positions a normal annotation below its viewport rectangle in a body portal", () => {
    mockLayout();
    const { panel, container } = openMeasuredEssay();
    expect(panel).toHaveAttribute("data-placement", "below");
    expect(panel).toHaveStyle({ top: "128px", left: "200px", width: "360px" });
    expect(panel.parentElement).toBe(document.body);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
  });

  it("flips above an annotation near the bottom", () => {
    mockLayout({ y: 750 });
    const { panel } = openMeasuredEssay();
    expect(panel).toHaveAttribute("data-placement", "above");
    expect(panel).toHaveStyle({ top: "542px" });
    expect(Number.parseFloat(panel.style.top) + 200).toBeLessThan(786);
  });

  it("constrains a tall panel to available space for internal scrolling", () => {
    mockLayout({ y: 350, panelHeight: 900 });
    const { panel } = openMeasuredEssay();
    expect(panel).toHaveAttribute("data-placement", "below");
    expect(panel).toHaveStyle({ top: "378px", maxHeight: "408px" });
    expect(Number.parseFloat(panel.style.top) + Number.parseFloat(panel.style.maxHeight)).toBe(786);
    expect(within(panel).getByText("people tend")).toBeInTheDocument();
    expect(within(panel).getByText("Use a plural verb.")).toBeInTheDocument();
  });

  it.each([{ x: 980, left: "626px" }, { x: -20, left: "14px" }])("clamps horizontal position at x=$x", ({ x, left }) => {
    mockLayout({ x });
    expect(openMeasuredEssay().panel).toHaveStyle({ left });
  });

  it("fits very narrow viewports without horizontal overflow", () => {
    mockLayout({ x: 220, viewportWidth: 240 });
    expect(openMeasuredEssay().panel).toHaveStyle({ width: "212px", left: "14px" });
  });

  it("uses right-aligned anchors for RTL text while retaining viewport margins", () => {
    mockLayout({ x: 600, width: 100 });
    render(<AnnotatedEssay content="people tends" annotations={[issue]} />);
    const anchor = screen.getByRole("button", { name: /people tends/ });
    anchor.style.direction = "rtl";
    fireEvent.mouseEnter(anchor);
    const panel = screen.getByRole("dialog");
    expect(panel.style.left).toBe("340px");
  });

  it("recalculates placement after viewport resize", () => {
    mockLayout({ y: 200 });
    const { panel } = openMeasuredEssay();
    expect(panel).toHaveAttribute("data-placement", "below");
    vi.stubGlobal("innerHeight", 300);
    fireEvent(window, new Event("resize"));
    expect(panel).toHaveAttribute("data-placement", "above");
    expect(panel).toHaveStyle({ top: "14px", maxHeight: "178px" });
  });

  it("recalculates placement when an ancestor container scrolls", () => {
    const anchor = mockLayout();
    const { panel, container } = openMeasuredEssay();
    anchor.y = 750;
    fireEvent.scroll(container);
    expect(panel).toHaveAttribute("data-placement", "above");
    expect(panel).toHaveStyle({ top: "542px" });
  });

  it("respects the visible viewport when a mobile viewport changes", () => {
    mockLayout({ y: 450 });
    const viewport = Object.assign(new EventTarget(), { offsetLeft: 0, offsetTop: 100, width: 320, height: 400 });
    vi.stubGlobal("visualViewport", viewport);
    const { panel } = openMeasuredEssay();
    expect(panel).toHaveStyle({ width: "292px", left: "14px", top: "242px" });
    viewport.offsetTop = 200;
    act(() => viewport.dispatchEvent(new Event("scroll")));
    expect(panel.style.top).toBe("242px");
    expect(panel.style.maxHeight).toBe("228px");
  });

  it("allows a hovered pointer to cross into the portal and activate View feedback", () => {
    vi.useFakeTimers();
    mockLayout();
    const onViewFeedback = vi.fn();
    const { container } = render(<AnnotatedEssay content="people tends" annotations={[issue]} onViewFeedback={onViewFeedback} />);
    fireEvent.mouseEnter(screen.getByRole("button", { name: /people tends/ }));
    const panel = screen.getByRole("dialog");
    fireEvent.mouseLeave(container.firstElementChild!, { relatedTarget: document.body });
    fireEvent.mouseEnter(panel);
    act(() => vi.advanceTimersByTime(200));
    fireEvent.click(within(panel).getByRole("button", { name: "View feedback" }));
    expect(onViewFeedback).toHaveBeenCalledWith(issue.id);
  });

  it("keeps a pinned portal usable and restores anchor focus on Escape", () => {
    mockLayout();
    const onViewFeedback = vi.fn();
    const { container } = render(<AnnotatedEssay content="people tends" annotations={[issue]} onViewFeedback={onViewFeedback} />);
    const anchor = screen.getByRole("button", { name: /people tends/ });
    fireEvent.click(anchor);
    fireEvent.mouseLeave(container.firstElementChild!);
    const panel = screen.getByRole("dialog");
    const action = within(panel).getByRole("button", { name: "View feedback" });
    act(() => action.focus());
    fireEvent.click(action);
    expect(onViewFeedback).toHaveBeenCalledWith(issue.id);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(action, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(anchor).toHaveFocus();
  });

  it("removes open-panel listeners on close and unmount", () => {
    mockLayout();
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = openMeasuredEssay();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
    expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function), true);
    fireEvent.click(screen.getByRole("button", { name: /people tends/ }));
    remove.mockClear();
    unmount();
    expect(remove).toHaveBeenCalledWith("scroll", expect.any(Function), true);
  });
});
