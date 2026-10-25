import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LoopingTicker, tickerLayout } from "@/components/ui/looping-ticker";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("continuous footer loop", () => {
  it("overfills one full copy at every screen width and keeps a constant reading speed", () => {
    for (const viewport of [390, 768, 1440, 2827, 3840, 5120]) {
      for (const unit of [280, 480, 620]) {
        const { repeats, duration } = tickerLayout(viewport, unit);
        expect(repeats * unit).toBeGreaterThan(viewport);
        expect(repeats * unit / duration).toBeCloseTo(48);
      }
    }
  });

  it("keeps both copies identical after a viewport resize or font/locale width change", () => {
    let width = 2827, unitWidth = 480;
    let resized: ResizeObserverCallback;
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: ResizeObserverCallback) { resized = callback; }
      observe() {} disconnect = disconnect;
    });
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockImplementation(function (this: HTMLElement) { return this.classList.contains("gravity-footer-ticker") ? width : 0; });
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(() => ({ width: unitWidth } as DOMRect));
    const { container, unmount } = render(<LoopingTicker>Practice <i /> Keep going <i /></LoopingTicker>);
    const checkCopies = () => {
      const groups = [...container.querySelectorAll(".gravity-footer-ticker-group")];
      expect(groups).toHaveLength(2);
      expect(groups[0].textContent).toBe(groups[1].textContent);
      expect(groups[0].children.length * unitWidth).toBeGreaterThan(width);
      expect(groups[0].children.length).toBe(groups[1].children.length);
    };
    checkCopies();
    expect(container.querySelector(".gravity-footer-ticker-group")!.children).toHaveLength(7);
    act(() => { width = 390; resized([], {} as ResizeObserver); });
    checkCopies();
    act(() => { width = 3840; unitWidth = 620; resized([], {} as ResizeObserver); });
    checkCopies();
    expect(container.querySelector(".gravity-footer-ticker-group")!.children).toHaveLength(8);
    expect(container.querySelector(".gravity-footer-ticker")!.getAttribute("style")).toContain(`${8 * 620 / 48}s`);
    unmount(); expect(disconnect).toHaveBeenCalledOnce();
  });
});
