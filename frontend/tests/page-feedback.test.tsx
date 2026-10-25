import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PageError from "@/app/error";
import Loading from "@/app/loading";
import { DataLoadNotice } from "@/components/ui/data-load-notice";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("page loading and recovery feedback", () => {
  it("retries a failed segment without displaying internal error details", () => {
    const retry = vi.fn();
    render(<PageError error={new Error("private backend detail")} retry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This page could not be loaded");
    expect(screen.queryByText("private backend detail")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("marks a pending route as busy with a readable loading status", () => {
    render(<Loading />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Loading your workspace");
  });

  it("refreshes partially loaded content through the existing router", () => {
    render(<DataLoadNotice />);
    expect(screen.getByRole("alert")).toHaveTextContent("Some practice content could not be loaded");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(refresh).toHaveBeenCalledOnce();
  });
});
