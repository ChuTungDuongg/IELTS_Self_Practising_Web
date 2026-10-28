import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { BandTrend } from "@/features/analytics/band-trend";
import type { AnalyticsDashboard } from "@/lib/api/analytics";
import { renderWithLocale } from "./locale-test-utils";

type TrendPoint = AnalyticsDashboard["trends"][number];
const point = (attempt_id: string, overrides: Partial<TrendPoint> = {}): TrendPoint => ({
  attempt_id, skill: "READING", band_score: 6, attempted_at: "2026-10-01T00:00:00Z",
  test_title: `Fictional test ${attempt_id}`, version_number: 1, ...overrides,
});
const chart = () => screen.getByRole("img", { name: "Band score trend from 0 to 9" });

beforeEach(() => window.localStorage.clear());

describe("Band trend", () => {
  it("connects consecutive observations separately for all four skills", () => {
    render(<BandTrend points={[
      point("r-last", { band_score: 7, attempted_at: "2026-10-11T00:00:00Z" }),
      point("l-last", { skill: "LISTENING", band_score: 8, attempted_at: "2026-10-10T00:00:00Z" }),
      point("w-last", { skill: "WRITING", band_score: 6.5, attempted_at: "2026-10-09T00:00:00Z" }),
      point("s-last", { skill: "SPEAKING", band_score: 7.5, attempted_at: "2026-10-08T00:00:00Z" }),
      point("r-first", { band_score: 5 }),
      point("l-first", { skill: "LISTENING", band_score: 6, attempted_at: "2026-10-02T00:00:00Z" }),
      point("w-first", { skill: "WRITING", band_score: 5.5, attempted_at: "2026-10-03T00:00:00Z" }),
      point("s-first", { skill: "SPEAKING", band_score: 6.5, attempted_at: "2026-10-04T00:00:00Z" }),
    ]} />);

    const lines = [...chart().querySelectorAll("polyline")];
    expect(lines).toHaveLength(4);
    expect(lines.map(line => line.getAttribute("data-skill"))).toEqual(["READING", "LISTENING", "WRITING", "SPEAKING"]);
    for (const line of lines) {
      const coordinates = line.getAttribute("points")!.split(" ").map(pair => pair.split(",").map(Number));
      expect(coordinates).toHaveLength(2);
      expect(coordinates[0][0]).toBeLessThan(coordinates[1][0]);
      expect(coordinates[0][1]).toBeGreaterThan(coordinates[1][1]);
    }
    const ends = lines.map(line => line.getAttribute("points")!.split(" ").map(pair => Number(pair.split(",")[0])));
    const span = ends[0][1] - ends[0][0];
    ends.forEach((pair, index) => {
      expect((pair[0] - ends[0][0]) / span).toBeCloseTo([0, .1, .2, .3][index]);
      expect((pair[1] - ends[0][0]) / span).toBeCloseTo([1, .9, .8, .7][index]);
    });
    expect(chart().querySelectorAll("circle")).toHaveLength(2);
    expect(chart().querySelectorAll("rect")).toHaveLength(2);
    expect(chart().querySelectorAll("path")).toHaveLength(4);
    const legend = screen.getByRole("list", { name: "Skill" });
    for (const skill of ["Reading", "Listening", "Writing", "Speaking"]) expect(within(legend).getByText(skill)).toBeInTheDocument();
    expect(screen.queryByText("Overall")).not.toBeInTheDocument();
  });

  it("uses elapsed time for x positions and keeps equal timestamps in stable order", () => {
    const points = [
      point("last", { attempted_at: "2026-10-11T00:00:00Z" }),
      point("same-a", { band_score: 5 }),
      point("middle", { attempted_at: "2026-10-02T00:00:00Z" }),
      point("same-b", { band_score: 7 }),
    ];
    const originalOrder = points.map(item => item.attempt_id);
    render(<BandTrend points={points} />);
    const x = [...chart().querySelectorAll("circle")].map(mark => Number(mark.getAttribute("cx")));
    expect(x).toHaveLength(4);
    expect(x[0]).toBe(x[1]);
    expect((x[2] - x[0]) / (x[3] - x[0])).toBeCloseTo(.1);
    fireEvent.click(screen.getByText("View score details"));
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map(row => within(row).getAllByRole("cell")[2].textContent)).toEqual([
      "Fictional test same-a", "Fictional test same-b", "Fictional test middle", "Fictional test last",
    ]);
    expect(points.map(item => item.attempt_id)).toEqual(originalOrder);
  });

  it("filters invalid dates and bands from both the chart and score table", () => {
    const points = [
      point("zero", { band_score: 0 }), point("nine", { band_score: 9 }),
      point("date", { attempted_at: "invalid-date" }),
      point("null", { band_score: null as unknown as number }),
      point("nan", { band_score: Number.NaN }), point("infinite", { band_score: Infinity }),
      point("negative", { band_score: -.5 }), point("above-nine", { band_score: 9.5 }),
      point("overall", { skill: "OVERALL" as TrendPoint["skill"] }),
    ];
    expect(() => render(<BandTrend points={points} />)).not.toThrow();
    expect(chart().querySelectorAll("circle")).toHaveLength(2);
    expect(chart().innerHTML).not.toMatch(/NaN|Infinity/);
    fireEvent.click(screen.getByText("View score details"));
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(table).toHaveTextContent("Fictional test zero");
    expect(table).toHaveTextContent("Fictional test nine");
    expect(table).toHaveTextContent("0.0");
    expect(table).toHaveTextContent("9.0");
    expect(table).not.toHaveTextContent("Fictional test overall");
  });

  it("reveals the actual timestamp, skill, band and authored title on hover and keyboard focus", () => {
    render(<BandTrend points={[point("detail", {
      skill: "SPEAKING", band_score: 6.5, attempted_at: "2026-10-02T01:30:15Z", test_title: "Fictional <speaking> test",
    })]} />);
    const mark = screen.getByRole("button", { name: /Speaking · 6.5 · 02 Oct 2026.*08:30:15.*Fictional <speaking> test/ });
    expect(mark.tagName).toBe("BUTTON");
    expect(mark.closest('[role="img"]')).toBeNull();
    expect(mark).toHaveAttribute("tabindex", "0");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(mark);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("Speaking · 6.5");
    expect(tooltip).toHaveTextContent("02 Oct 2026");
    expect(tooltip).toHaveTextContent("08:30:15");
    expect(tooltip).toHaveTextContent("Fictional <speaking> test");
    expect(tooltip.querySelector("time")).toHaveAttribute("datetime", "2026-10-02T01:30:15Z");
    expect(tooltip.querySelector("speaking")).toBeNull();
    fireEvent.mouseLeave(mark);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.focus(mark);
    fireEvent.mouseLeave(mark);
    expect(screen.getByRole("tooltip")).toHaveTextContent("08:30:15");
    expect(mark).toHaveAttribute("aria-describedby", screen.getByRole("tooltip").id);
    fireEvent.blur(mark);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("uses one tab stop and navigates observed points chronologically with arrow, Home and End keys", () => {
    render(<BandTrend points={[
      point("last", { attempted_at: "2026-10-11T00:00:00Z" }),
      point("first", { skill: "WRITING" }),
      point("middle", { skill: "LISTENING", attempted_at: "2026-10-02T00:00:00Z" }),
      point("same-time", { skill: "SPEAKING" }),
    ]} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.map(button => button.tabIndex)).toEqual([0, -1, -1, -1]);
    fireEvent.mouseEnter(buttons[3]);
    expect(buttons.map(button => button.tabIndex)).toEqual([0, -1, -1, -1]);
    fireEvent.mouseLeave(buttons[3]);
    fireEvent.click(buttons[0]);
    fireEvent.keyDown(buttons[0], { key: "ArrowRight" });
    expect(buttons[1]).toHaveFocus();
    expect(buttons[1].style.left).toBe(buttons[0].style.left);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Fictional test same-time");
    expect(buttons.map(button => button.tabIndex)).toEqual([-1, 0, -1, -1]);
    fireEvent.keyDown(buttons[1], { key: "End" });
    expect(buttons[3]).toHaveFocus();
    fireEvent.keyDown(buttons[3], { key: "ArrowRight" });
    expect(buttons[3]).toHaveFocus();
    fireEvent.keyDown(buttons[3], { key: "ArrowLeft" });
    expect(buttons[2]).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Fictional test middle");
    fireEvent.keyDown(buttons[2], { key: "Home" });
    expect(buttons[0]).toHaveFocus();
    fireEvent.keyDown(buttons[0], { key: "ArrowLeft" });
    expect(buttons[0]).toHaveFocus();
    fireEvent.keyDown(buttons[0], { key: "End" });
    fireEvent.blur(buttons[3]);
    expect(buttons.map(button => button.tabIndex)).toEqual([-1, -1, -1, 0]);
  });

  it("keeps the scale bounded and date labels compact without a spurious single-point line", () => {
    const { rerender } = render(<BandTrend points={[point("one")]} />);
    expect(chart().querySelectorAll("polyline")).toHaveLength(0);
    expect(chart().querySelectorAll("circle")).toHaveLength(1);
    const yTicks = [...chart().querySelectorAll("text")].map(label => label.textContent).filter(label => /^\d(?:\.\d)?$/.test(label ?? ""));
    expect(yTicks.length).toBeGreaterThanOrEqual(4);
    expect(yTicks.length).toBeLessThanOrEqual(6);
    expect(yTicks).toContain("0");
    expect(yTicks).toContain("9");
    rerender(<BandTrend points={[
      point("start", { attempted_at: "2025-01-01T00:00:00Z" }),
      point("end", { attempted_at: "2026-10-28T00:00:00Z" }),
    ]} />);
    const dates = [...chart().querySelectorAll("text")].filter(label => /[A-Za-z]/.test(label.textContent ?? ""));
    expect(dates.length).toBeGreaterThanOrEqual(2);
    expect(dates.length).toBeLessThanOrEqual(4);
    expect(dates[0]).toHaveTextContent("01 Jan 2025");
    expect(dates.at(-1)).toHaveTextContent("28 Oct 2026");
  });

  it("localizes skill labels and date details while preserving score and authored title", () => {
    renderWithLocale(<BandTrend points={[point("locale", {
      skill: "WRITING", band_score: 6.5, attempted_at: "2026-10-02T01:30:15Z", test_title: "Fictional authored title",
    })]} />);
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    const mark = screen.getByRole("button", { name: /Viết · 6.5/ });
    fireEvent.focus(mark);
    expect(screen.getByRole("tooltip")).toHaveTextContent("08:30:15");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Fictional authored title");
    expect(screen.getByRole("img", { name: "Xu hướng điểm band từ 0 đến 9" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Xem chi tiết điểm"));
    expect(screen.getByRole("table")).toHaveTextContent("Viết");
    expect(screen.getByRole("table")).toHaveTextContent("6.5");
    expect(screen.getByRole("table")).toHaveTextContent("08:30:15");
  });
});
