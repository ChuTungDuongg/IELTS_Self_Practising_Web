import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReadingSplitPane } from "@/features/practice/reading-split-pane";

afterEach(() => vi.unstubAllGlobals());

describe("Reading Practice divider", () => {
  function renderPanes() {
    return render(<ReadingSplitPane id="panes"><article>Passage</article><section id="panes-questions"><input aria-label="Answer" defaultValue="Saved draft" /></section></ReadingSplitPane>);
  }
  it("resizes in both directions from the keyboard and retains child state and scroll", () => {
    const view = renderPanes();
    const separator = screen.getByRole("separator", { name: "Resize passage and questions" });
    const input = screen.getByRole("textbox");
    const passage = view.container.querySelector("article")!;
    const questions = view.container.querySelector("section")!;
    passage.scrollTop = 120; questions.scrollTop = 230;
    expect(separator).toHaveAttribute("aria-orientation", "vertical");
    expect(separator).toHaveAttribute("aria-valuenow", "50");
    fireEvent.keyDown(separator, { key: "ArrowRight", shiftKey: true });
    expect(separator).toHaveAttribute("aria-valuenow", "60");
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(separator).toHaveAttribute("aria-valuenow", "58");
    fireEvent.keyDown(separator, { key: "Home" });
    expect(separator).toHaveAttribute("aria-valuenow", "30");
    fireEvent.keyDown(separator, { key: "End" });
    expect(separator).toHaveAttribute("aria-valuenow", "70");
    fireEvent.keyDown(separator, { key: "Enter" });
    expect(separator).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByRole("textbox")).toBe(input);
    expect(input).toHaveValue("Saved draft");
    expect([passage.scrollTop, questions.scrollTop]).toEqual([120, 230]);
  });
  it.each(["mouse", "touch"])("captures %s pointer movement, clamps bounds and stops on cancellation", pointerType => {
    class Pointer extends MouseEvent {
      pointerId: number;
      constructor(type: string, options: PointerEventInit = {}) { super(type, options); this.pointerId = options.pointerId ?? 1; }
    }
    vi.stubGlobal("PointerEvent", Pointer);
    const view = renderPanes();
    const separator = screen.getByRole("separator");
    vi.spyOn(view.container.firstElementChild!, "getBoundingClientRect").mockReturnValue({ left: 100, width: 1200 } as DOMRect);
    const capture = vi.fn(); Object.defineProperty(separator, "setPointerCapture", { value: capture });
    fireEvent.pointerDown(separator, { pointerType, pointerId: 8, button: 0 });
    expect(capture).toHaveBeenCalledWith(8);
    fireEvent.pointerMove(separator, { pointerId: 8, clientX: 1500 });
    expect(separator).toHaveAttribute("aria-valuenow", "70");
    fireEvent.pointerMove(separator, { pointerId: 8, clientX: 0 });
    expect(separator).toHaveAttribute("aria-valuenow", "30");
    fireEvent.pointerCancel(separator, { pointerId: 8 });
    fireEvent.pointerMove(separator, { pointerId: 8, clientX: 1500 });
    expect(separator).toHaveAttribute("aria-valuenow", "30");
    expect(view.container.firstElementChild).not.toHaveAttribute("data-resizing");
  });
  it("adapts minimum widths to viewport changes and disconnects its observer", () => {
    let resized!: ResizeObserverCallback;
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class { constructor(callback: ResizeObserverCallback) { resized = callback; } observe() {} disconnect = disconnect; });
    const view = renderPanes();
    const separator = screen.getByRole("separator");
    fireEvent.keyDown(separator, { key: "End" });
    act(() => resized([{ contentRect: { width: 700 } } as ResizeObserverEntry], {} as ResizeObserver));
    expect(Number(separator.getAttribute("aria-valuemin"))).toBe(49);
    expect(Number(separator.getAttribute("aria-valuenow"))).toBe(51);
    view.unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
