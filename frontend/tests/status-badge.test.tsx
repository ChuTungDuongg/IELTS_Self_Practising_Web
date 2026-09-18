import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "@/components/ui/status-badge";

describe("StatusBadge", () => {
  it("renders readable attempt states", () => {
    render(<StatusBadge status="AUTO_SUBMITTED" />);
    expect(screen.getByText("AUTO SUBMITTED")).toBeInTheDocument();
  });
});
