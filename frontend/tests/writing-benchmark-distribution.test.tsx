import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BenchmarkDistribution } from "@/features/writing-benchmark/distribution";
import { benchmarkSummarySchema } from "@/lib/api/writing-benchmark";
import { benchmarkSummary } from "./writing-benchmark-fixtures";
import { renderWithLocale } from "./locale-test-utils";

describe("benchmark distribution guidance", () => {
  it("shows complete-only histogram and split advice with legal lower bands", () => {
    window.localStorage.clear();
    const summary = benchmarkSummarySchema.parse(benchmarkSummary());
    const task = summary.tasks[0]; task.total = 12; task.complete = 10; task.draft = 2;
    task.split_counts = { DEV: 8, HOLDOUT: 2 };
    task.overall_distribution[4].actual = 2; task.overall_distribution[16].actual = 5;
    renderWithLocale(<BenchmarkDistribution summary={summary} />);
    const section = screen.getByRole("region", { name: "Task 1 distribution" });
    expect(within(section).getByText("10 complete · 2 draft · 12/100 slots")).toBeInTheDocument();
    expect(within(section).getByText("DEV: 8 / suggested 80")).toBeInTheDocument();
    expect(within(section).getByText("HOLDOUT: 2 / suggested 20")).toBeInTheDocument();
    expect(within(section).getByRole("row", { name: "8.0 5 8" })).toBeInTheDocument();
    expect(within(section).getByRole("row", { name: "2.0 2 —" })).toBeInTheDocument();
    expect(screen.getByText(/Guidance only/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("region", { name: "Phân bố Task 1" })).toBeInTheDocument();
  });
});
