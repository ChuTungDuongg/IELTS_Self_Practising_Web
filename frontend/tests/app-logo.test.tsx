import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AppLogo } from "@/components/ui/app-logo";

describe("AppLogo", () => {
  it("renders the full-color planet as decorative by default", () => {
    const { container } = render(<AppLogo />);
    const logo = container.querySelector("svg");

    expect(logo).toHaveClass("app-logo-primary");
    expect(logo).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelectorAll("circle")).toHaveLength(2);
    expect(container.querySelectorAll("path").length).toBeGreaterThanOrEqual(5);
  });

  it("supports monochrome and accessible standalone variants", () => {
    render(<AppLogo variant="monochrome" title="IELTS Studio planet logo" />);

    expect(screen.getByRole("img", { name: "IELTS Studio planet logo" })).toHaveClass("app-logo-monochrome");
  });

  it("keeps the icon variant compact", () => {
    const { container } = render(<AppLogo variant="icon" />);

    expect(container.querySelector("svg")).toHaveClass("app-logo-icon");
    expect(container.querySelectorAll("circle")).toHaveLength(1);
  });
});
