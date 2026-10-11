import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { renderWithLocale } from "./locale-test-utils";
import { LocaleProvider } from "@/lib/i18n/locale-provider";

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "light";
    window.localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("uses decorative moon and sun SVGs while preserving theme actions", () => {
    const { container } = render(<LocaleProvider><ThemeToggle /></LocaleProvider>);
    const lightAction = screen.getByRole("button", { name: "Use dark theme" });
    expect(lightAction).toHaveAttribute("title", "Use dark theme");
    expect(lightAction.textContent).not.toMatch(/[☾☀]/);
    const moon = lightAction.querySelector(".theme-light-label svg");
    const sun = lightAction.querySelector(".theme-dark-label svg");
    expect(moon).not.toBeNull();
    expect(sun).not.toBeNull();
    for (const icon of [moon, sun]) {
      expect(icon).toHaveClass("theme-icon");
      expect(icon).toHaveAttribute("aria-hidden", "true");
      expect(icon).toHaveAttribute("viewBox", "0 0 24 24");
      expect(icon).toHaveAttribute("width", "18");
      expect(icon).toHaveAttribute("height", "18");
    }
    expect(moon?.querySelector("path")).not.toBeNull();
    expect(sun?.querySelector("circle")).not.toBeNull();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    fireEvent.click(lightAction);
    expect(document.documentElement.dataset.theme).toBe("dark");
    const darkAction = screen.getByRole("button", { name: "Use light theme" });
    expect(darkAction).toHaveAttribute("title", "Use light theme");
    expect(container.querySelector(".theme-dark-label svg")).toBe(sun);
    fireEvent.click(darkAction);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("renders deterministic light markup and reconciles a bootstrapped dark root after mount", () => {
    document.documentElement.dataset.theme = "dark";
    expect(renderToString(<ThemeToggle />)).toContain('aria-label="Use dark theme"');
    render(<LocaleProvider><ThemeToggle /></LocaleProvider>);
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
  });

  it("switches and remembers the visual theme", () => {
    render(<LocaleProvider><ThemeToggle /></LocaleProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("ielts-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("ielts-theme")).toBe("light");
  });

  it("changes the shared document state even if preference cache writes fail", () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<LocaleProvider><ThemeToggle /></LocaleProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
    expect(read).toHaveBeenCalledWith("ielts-locale");
    expect(write).toHaveBeenCalledWith("ielts-accent", "PURPLE");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("localizes the next action without changing the selected theme", () => {
    renderWithLocale(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
    fireEvent.click(screen.getByRole("button", { name: "Dùng giao diện tối" }));
    expect(screen.getByRole("button", { name: "Dùng giao diện sáng" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Switch to English" }));
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
