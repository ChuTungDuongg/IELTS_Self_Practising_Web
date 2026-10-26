import { act, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { VietnamClock } from "@/components/ui/vietnam-clock";

afterEach(() => vi.useRealTimers());

it("shows GMT+7 independently of the browser timezone and updates across midnight", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-26T16:59:59Z"));
  const view = render(<VietnamClock />);
  expect(screen.getByLabelText("Vietnam time: 23:59:59 GMT+7")).toHaveAttribute("datetime", "2026-10-26T16:59:59.000Z");
  act(() => { vi.advanceTimersByTime(1000); });
  expect(screen.getByLabelText("Vietnam time: 00:00:00 GMT+7")).toBeInTheDocument();
  view.unmount();
  expect(vi.getTimerCount()).toBe(0);
});

it("renders a stable server placeholder before hydration", () => {
  expect(renderToString(<VietnamClock />)).toContain("--:--:--");
});
