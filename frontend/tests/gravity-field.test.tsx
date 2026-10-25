import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GravityField } from "@/components/home/gravity/gravity-field";
import { GravityLanding } from "@/components/home/gravity/gravity-landing";

const mock = vi.hoisted(() => ({
  create: vi.fn(), active: vi.fn(), progress: vi.fn(), pointer: vi.fn(), scatter: vi.fn(), dispose: vi.fn(),
}));
vi.mock("@/components/home/gravity/load-scene", () => ({ loadGravityScene: async () => ({ createGravityScene: (...args: unknown[]) => mock.create(...args) }) }));
let media: MediaQueryList;
let reduced = false;
let saveData = false;
let intersect: IntersectionObserverCallback;
const disconnect = vi.fn();
function Field() { return <div className="gravity-story"><GravityField /><section data-gravity-section /></div>; }

beforeEach(() => {
  vi.clearAllMocks(); reduced = false; saveData = false;
  Object.defineProperty(navigator, "connection", { configurable: true, get: () => ({ saveData }) });
  const events = new EventTarget();
  media = { get matches() { return reduced; }, addEventListener: events.addEventListener.bind(events), removeEventListener: events.removeEventListener.bind(events), dispatchEvent: events.dispatchEvent.bind(events) } as MediaQueryList;
  vi.stubGlobal("matchMedia", () => media);
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect = disconnect; });
  vi.stubGlobal("IntersectionObserver", class { constructor(callback: IntersectionObserverCallback) { intersect = callback; } observe() {} unobserve() {} disconnect = disconnect; });
  mock.create.mockImplementation((_element, _lowPower, ready) => {
    ready(); return { setActive: mock.active, setProgress: mock.progress, setPointer: mock.pointer, scatter: mock.scatter, dispose: mock.dispose };
  });
});
afterEach(() => { vi.unstubAllGlobals(); delete (navigator as Navigator & { connection?: unknown }).connection; });

describe("homepage progressive scene", () => {
  it("keeps a complete static field and does not create WebGL with reduced motion", () => {
    reduced = true;
    const { container } = render(<Field />);
    expect(container.querySelectorAll(".gravity-static-sphere")).toHaveLength(20);
    expect(mock.create).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Pause motion" })).not.toBeInTheDocument();
  });
  it("does not load the renderer when data saving is requested", () => {
    saveData = true;
    render(<Field />);
    expect(mock.create).not.toHaveBeenCalled();
  });
  it("provides keyboard buttons, pauses offscreen, and does not resume offscreen", async () => {
    render(<Field />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Scatter spheres" }));
    expect(mock.scatter).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Pause motion" }));
    expect(mock.active).toHaveBeenLastCalledWith(false);
    act(() => intersect([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver));
    fireEvent.click(screen.getByRole("button", { name: "Resume motion" }));
    expect(mock.active).toHaveBeenLastCalledWith(false);
    act(() => intersect([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(mock.active).toHaveBeenLastCalledWith(true);
  });
  it("releases the scene and observers on Strict Mode remount and navigation away", async () => {
    const { unmount } = render(<StrictMode><Field /></StrictMode>);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    unmount();
    expect(mock.dispose).toHaveBeenCalledOnce();
    expect(disconnect).toHaveBeenCalled();
  });
  it("falls back after initialization failure without removing page content", async () => {
    mock.create.mockImplementationOnce(() => { throw new Error("WebGL unavailable"); });
    const { container } = render(<GravityLanding />);
    await waitFor(() => expect(container.querySelector(".gravity-stage")).toHaveAttribute("data-scene", "failed"));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Practice with purpose.");
    expect(screen.getByRole("link", { name: /^Start / })).toHaveAttribute("href", "/practice");
    expect(container.querySelectorAll("[data-gravity-section]")).toHaveLength(4);
  });
  it("tears down when the OS switches to reduced motion", async () => {
    render(<Field />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    act(() => { reduced = true; media.dispatchEvent(new Event("change")); });
    expect(mock.dispose).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Pause motion" })).not.toBeInTheDocument();
  });
  it("preserves a manual pause across OS preference changes and allows resuming", async () => {
    render(<Field />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Pause motion" }));
    act(() => { reduced = true; media.dispatchEvent(new Event("change")); });
    act(() => { reduced = false; media.dispatchEvent(new Event("change")); });
    expect(screen.getByRole("button", { name: "Resume motion" })).toBeInTheDocument();
    expect(mock.create).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "Resume motion" }));
    await waitFor(() => expect(mock.create).toHaveBeenCalledTimes(2));
  });
});
