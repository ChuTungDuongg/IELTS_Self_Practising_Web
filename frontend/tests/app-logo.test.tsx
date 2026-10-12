import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { AppLogo } from "@/components/ui/app-logo";

afterEach(() => { delete document.documentElement.dataset.accent; });

describe("BandPilot Compass Ribbon AppLogo", () => {
  it("renders four filled ribbons with a stable brand gradient and a decorative default", () => {
    const { container } = render(<AppLogo />);
    const logo = container.querySelector("svg")!;

    expect(logo).toHaveClass("app-logo-primary");
    expect(logo).toHaveAttribute("viewBox", "0 0 64 64");
    expect(logo).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("img")).toBeNull();
    expect(logo.querySelectorAll("path")).toHaveLength(4);
    expect(logo.querySelectorAll("circle")).toHaveLength(0);
    expect([...logo.querySelectorAll("stop")].map(stop => stop.getAttribute("stop-color"))).toEqual(["#4F46E5", "#3B82F6", "#22B8CF"]);
  });

  it("supports an accessible standalone title and monochrome currentColor", () => {
    render(<AppLogo variant="monochrome" title="BandPilot Compass Ribbon logo" />);
    const logo = screen.getByRole("img", { name: "BandPilot Compass Ribbon logo" });
    expect(logo).toHaveClass("app-logo-monochrome");
    expect(logo).not.toHaveAttribute("aria-hidden");
    expect(logo.querySelector("title")).toHaveTextContent("BandPilot Compass Ribbon logo");
    expect(logo.querySelector("g")).toHaveAttribute("fill", "currentColor");
    expect(logo.querySelector("linearGradient")).toBeNull();
  });

  it("isolates gradient references across repeated logos and preserves color when accents change", () => {
    const { container, rerender } = render(<><AppLogo /><AppLogo variant="icon" /></>);
    const ids = [...container.querySelectorAll("linearGradient")].map(gradient => gradient.id);
    expect(new Set(ids).size).toBe(2);
    container.querySelectorAll("svg").forEach((logo, index) => {
      expect(logo.querySelector("g")).toHaveAttribute("fill", `url(#${ids[index]})`);
    });
    const stops = [...container.querySelectorAll("stop")].map(stop => stop.getAttribute("stop-color"));
    document.documentElement.dataset.accent = "red";
    rerender(<><AppLogo /><AppLogo variant="icon" /></>);
    expect([...container.querySelectorAll("stop")].map(stop => stop.getAttribute("stop-color"))).toEqual(stops);
    expect(container.querySelector(".app-logo-icon")?.querySelectorAll("path")).toHaveLength(4);
  });

  it("uses the same mark in the app icon and both public SVG assets", () => {
    const { container } = render(<AppLogo />);
    const ribbons = [...container.querySelectorAll("path")].map(path => [path.getAttribute("d"), path.getAttribute("transform")]);
    for (const file of ["src/app/icon.svg", "public/brand/bandpilot-compass-ribbon.svg", "public/brand/bandpilot-compass-ribbon-monochrome.svg"]) {
      const asset = new DOMParser().parseFromString(readFileSync(resolve(process.cwd(), file), "utf8"), "image/svg+xml");
      expect(asset.querySelector("parsererror")).toBeNull();
      expect([...asset.querySelectorAll("path")].map(path => [path.getAttribute("d"), path.getAttribute("transform")])).toEqual(ribbons);
      expect(asset.querySelector("text")).toBeNull();
    }
  });
});
