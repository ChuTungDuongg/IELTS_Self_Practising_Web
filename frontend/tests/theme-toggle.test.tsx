import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { renderWithLocale } from "./locale-test-utils";

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.dataset.theme = "light";
    window.localStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders deterministic light markup and reconciles a bootstrapped dark root after mount", () => {
    document.documentElement.dataset.theme = "dark";
    expect(renderToString(<ThemeToggle />)).toContain('aria-label="Use dark theme"');
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
  });

  it("switches and remembers the visual theme", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("ielts-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "Use light theme" }));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(window.localStorage.getItem("ielts-theme")).toBe("light");
  });

  it("changes the current document even if storage writes fail, without accessing locale", () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeInTheDocument();
    expect(read).not.toHaveBeenCalled();
    expect(write).toHaveBeenCalledExactlyOnceWith("ielts-theme", "dark");
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
