import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GravityField } from "@/components/home/gravity/gravity-field";
import { GravityLanding } from "@/components/home/gravity/gravity-landing";
import { GlobalHeader } from "@/components/ui/global-header";
import { PersonalizationProvider } from "@/features/personalization/personalization-provider";

const mock = vi.hoisted(() => ({
  create: vi.fn(), active: vi.fn(), progress: vi.fn(), pointer: vi.fn(), scatter: vi.fn(), dispose: vi.fn(),
}));
vi.mock("@/components/home/gravity/load-scene", () => ({ loadGravityScene: async () => ({ createGravityScene: (...args: unknown[]) => mock.create(...args) }) }));
vi.mock("@/features/auth/auth-provider", () => ({ useAuth: () => ({ user: null, loading: false, sessionError: null, logout: vi.fn() }) }));
let media: MediaQueryList;
let reduced = false;
let saveData = false;
let intersect: IntersectionObserverCallback;
const disconnect = vi.fn();
function Field() { return <div className="gravity-story"><GravityField /><section data-gravity-section /></div>; }

beforeEach(() => {
  vi.clearAllMocks(); reduced = false; saveData = false;
  localStorage.clear(); document.documentElement.dataset.theme = "light";
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
  it("preserves the scene, manual pause and scroll when guest language or appearance changes", async () => {
    const scroll = vi.fn(); vi.stubGlobal("scrollTo", scroll);
    const { container } = render(<PersonalizationProvider><GlobalHeader pathname="/" /><GravityLanding /></PersonalizationProvider>);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    const stage = container.querySelector(".gravity-stage");
    fireEvent.click(screen.getByRole("button", { name: "Scatter spheres" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause motion" }));
    fireEvent.click(screen.getByRole("button", { name: "VI" }));
    fireEvent.click(screen.getByRole("button", { name: "Dùng giao diện tối" }));
    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByRole("button", { name: "Resume motion" })).toBeInTheDocument();
    expect(container.querySelector(".gravity-stage")).toBe(stage);
    expect(mock.create).toHaveBeenCalledOnce();
    expect(mock.dispose).not.toHaveBeenCalled();
    expect(mock.scatter).toHaveBeenCalledOnce();
    expect(mock.active).toHaveBeenLastCalledWith(false);
    expect(scroll).not.toHaveBeenCalled();
  });
  it("autoplays the requested homepage motion at lower quality with reduced motion", async () => {
    reduced = true;
    const { container } = render(<Field />);
    expect(container.querySelectorAll(".gravity-static-sphere")).toHaveLength(20);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    expect(mock.create.mock.calls[0][1]).toBe(true);
    expect(screen.getByRole("button", { name: "Pause motion" })).toBeInTheDocument();
  });
  it("does not load the renderer when data saving is requested", () => {
    saveData = true;
    render(<Field />);
    expect(mock.create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Resume motion" }));
    return waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
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
  it("keeps the explicitly requested animation running when OS preferences change", async () => {
    render(<Field />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    act(() => { reduced = true; media.dispatchEvent(new Event("change")); });
    expect(mock.dispose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Pause motion" })).toBeInTheDocument();
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
    expect(mock.active).toHaveBeenLastCalledWith(true);
    expect(mock.create).toHaveBeenCalledOnce();
  });

  it("navigates to chapters three and four with one click and accounts for the fixed header", async () => {
    const scroll = vi.fn(); vi.stubGlobal("scrollTo", scroll);
    const { container } = render(<GravityLanding />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    const header = document.createElement("header"); header.className = "app-header";
    header.getBoundingClientRect = () => ({ height: 96 } as DOMRect); document.body.append(header);
    const sections = container.querySelectorAll<HTMLElement>("[data-gravity-section]");
    sections[2].getBoundingClientRect = () => ({ top: 1800 } as DOMRect);
    sections[3].getBoundingClientRect = () => ({ top: 2700 } as DOMRect);
    fireEvent.click(screen.getByRole("link", { name: "3. See progress take shape." }));
    expect(scroll).toHaveBeenLastCalledWith({ top: 1688, behavior: "smooth" });
    fireEvent.click(screen.getByRole("link", { name: "4. Find your focus." }));
    expect(scroll).toHaveBeenLastCalledWith({ top: 2588, behavior: "smooth" });
    expect(scroll).toHaveBeenCalledTimes(2);
    header.remove();
  });

  it("automatically aligns the next chapter once scrolling crosses its approach line", async () => {
    vi.stubGlobal("innerHeight", 768);
    vi.stubGlobal("scrollY", 0);
    const scroll = vi.fn(); vi.stubGlobal("scrollTo", scroll);
    const { container } = render(<GravityLanding />);
    await waitFor(() => expect(mock.create).toHaveBeenCalledOnce());
    const story = container.querySelector<HTMLElement>(".gravity-story")!;
    story.getBoundingClientRect = () => ({ top: -window.scrollY, bottom: 3600 - window.scrollY } as DOMRect);
    const header = document.createElement("header"); header.className = "app-header";
    header.getBoundingClientRect = () => ({ height: 96 } as DOMRect); document.body.append(header);
    const sections = container.querySelectorAll<HTMLElement>("[data-gravity-section]");
    [0, 700, 1600, 2650].forEach((top, index) => {
      sections[index].getBoundingClientRect = () => ({ top: top - window.scrollY } as DOMRect);
    });
    vi.stubGlobal("scrollY", 250); fireEvent.scroll(window);
    await new Promise(resolve => setTimeout(resolve, 25));
    expect(scroll).not.toHaveBeenCalled();
    vi.stubGlobal("scrollY", 300); fireEvent.scroll(window);
    await waitFor(() => expect(scroll).toHaveBeenCalledWith({ top: 588, behavior: "smooth" }));
    expect(screen.getByRole("link", { name: "2. Build every skill." })).toHaveAttribute("aria-current", "step");
    header.remove();
  });
});
