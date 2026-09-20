import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/page";
import { InteractivePlanet } from "@/components/home/interactive-planet";

vi.mock("@/lib/api/history", () => ({
  getHistory: vi.fn().mockResolvedValue({ items: [], groups: [], total: 0 }),
}));

vi.mock("@/lib/api/tests", () => ({
  getTests: vi.fn().mockResolvedValue([]),
}));

type MediaQueryOptions = {
  reducedMotion?: boolean;
  finePointer?: boolean;
};

function installMatchMedia({ reducedMotion = false, finePointer = true }: MediaQueryOptions = {}) {
  vi.stubGlobal("matchMedia", vi.fn((query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reducedMotion : finePointer,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })));
}

describe("InteractivePlanet", () => {
  let animationFrames: FrameRequestCallback[];

  beforeEach(() => {
    animationFrames = [];
    installMatchMedia();
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    }));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses the planet AppLogo and remains purely decorative", () => {
    const { container } = render(<InteractivePlanet />);
    const orbit = container.querySelector(".home-orbit-interactive");

    expect(orbit).toHaveAttribute("aria-hidden", "true");
    expect(orbit?.querySelector(".home-orbit-core .app-logo-icon")).toBeInTheDocument();
    expect(orbit).not.toHaveAttribute("tabindex");
  });

  it("updates CSS motion variables without cancelling pointer actions", () => {
    const { container } = render(<InteractivePlanet />);
    const orbit = container.querySelector<HTMLElement>(".home-orbit-interactive")!;
    vi.spyOn(orbit, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 300,
      bottom: 280,
      width: 300,
      height: 280,
      toJSON: () => ({}),
    });

    fireEvent.pointerEnter(orbit, { clientX: 270, clientY: 35 });
    expect(orbit).toHaveClass("is-active");
    expect(animationFrames).toHaveLength(1);

    animationFrames.shift()?.(16);
    expect(Number.parseFloat(orbit.style.getPropertyValue("--planet-shift-x"))).toBeGreaterThan(0);
    expect(Number.parseFloat(orbit.style.getPropertyValue("--planet-shift-y"))).toBeLessThan(0);

    const press = new Event("pointerdown", { bubbles: true, cancelable: true });
    orbit.dispatchEvent(press);
    expect(press.defaultPrevented).toBe(false);

    fireEvent.pointerLeave(orbit);
    expect(orbit).not.toHaveClass("is-active");
  });

  it("stays static when reduced motion is requested", () => {
    installMatchMedia({ reducedMotion: true });
    const { container } = render(<InteractivePlanet />);
    const orbit = container.querySelector<HTMLElement>(".home-orbit-interactive")!;

    fireEvent.pointerEnter(orbit, { clientX: 200, clientY: 20 });
    fireEvent.pointerMove(orbit, { clientX: 250, clientY: 10 });

    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(orbit).not.toHaveClass("is-active");
    expect(orbit.style.getPropertyValue("--planet-shift-x")).toBe("0.000px");
    expect(orbit.style.getPropertyValue("--planet-shift-y")).toBe("0.000px");
  });

  it("is rendered by the server homepage without changing its actions", async () => {
    render(await DashboardPage());

    expect(document.querySelector(".home-orbit-interactive")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start practicing/i })).toHaveAttribute("href", "/library");
    expect(screen.getByRole("link", { name: /open builder/i })).toHaveAttribute("href", "/admin/tests");
  });
});
