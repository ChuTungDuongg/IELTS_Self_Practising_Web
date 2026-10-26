import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GoalCountdown } from "@/components/home/goal-countdown";
import { renderWithLocale } from "./locale-test-utils";

afterEach(() => vi.useRealTimers());

it("counts days, hours, minutes and seconds to the target date at midnight GMT+7", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-26T15:58:57Z"));
  const view = render(<GoalCountdown date="2026-10-28" />);
  const countdown = screen.getByRole("timer", { name: "Time until target test date" });
  expect(countdown).toHaveTextContent("1day01hours01minutes03seconds");
  expect(screen.getByText("Until 00:00 GMT+7 on your target date")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(1000));
  expect(countdown).toHaveTextContent("1day01hours01minutes02seconds");
  act(() => vi.setSystemTime(new Date("2026-10-27T16:59:59Z")));
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(countdown).toHaveTextContent("0days00hours00minutes01seconds");
  act(() => vi.advanceTimersByTime(1000));
  expect(countdown).toHaveTextContent("0days00hours00minutes00seconds");
  expect(screen.getByText("Your target date has arrived")).toBeInTheDocument();
  view.unmount(); expect(vi.getTimerCount()).toBe(0);
});

it("updates the date and locale without keeping a stale countdown", () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-26T17:00:00Z"));
  localStorage.clear();
  const view = renderWithLocale(<GoalCountdown date="2026-10-28" />);
  expect(screen.getByRole("timer")).toHaveTextContent("1day00hours00minutes00seconds");
  act(() => screen.getByRole("button", { name: "Switch to Vietnamese" }).click());
  expect(screen.getByRole("timer", { name: "Thời gian đến ngày thi mục tiêu" })).toHaveTextContent("1ngày00giờ00phút00giây");
  view.unmount();
  render(<GoalCountdown date="2026-10-29" />);
  expect(screen.getByRole("timer")).toHaveTextContent("2days00hours00minutes00seconds");
});

it.each(["not-a-date", "2026-02-30", "2026-13-01"])("does not show a misleading timer for invalid date %s", date => {
  const view = render(<GoalCountdown date={date} />);
  expect(view.container).toBeEmptyDOMElement();
});
