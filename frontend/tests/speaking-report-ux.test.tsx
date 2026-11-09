import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { SpeakingBenchmarkReports } from "@/features/speaking-benchmark/evaluation/reports";
import { ReportCharts } from "@/features/speaking-benchmark/evaluation/report-charts";
import { LabGuide } from "@/features/speaking-benchmark/lab-guide";
import * as api from "@/lib/api/speaking-benchmark-grading";
import { en } from "@/lib/i18n/en";
import { vi as vietnamese } from "@/lib/i18n/vi";
import { emptyReport, filledReport, reportComparisons } from "./ux-preview/report-fixtures";
import { comparison } from "./ux-preview/workflow-fixtures";
import { renderWithLocale } from "./locale-test-utils";

vi.mock("@/lib/api/speaking-benchmark-grading", async original => ({ ...await original<typeof api>(), reportSummary: vi.fn(), reportSamples: vi.fn() }));
const samplePage = (items = reportComparisons.slice(0, 2)) => ({
  items, total: 24, offset: 0, limit: 25, configuration: comparison.configuration,
  chart_points: reportComparisons, chart_limit: 500, chart_sampled: false,
  outliers: [reportComparisons[4]],
});
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(api.reportSummary).mockResolvedValue(filledReport);
  vi.mocked(api.reportSamples).mockResolvedValue(samplePage());
});

it("replaces a first-run report with useful next steps instead of empty charts and tables", async () => {
  vi.mocked(api.reportSummary).mockResolvedValue(emptyReport);
  vi.mocked(api.reportSamples).mockResolvedValue({ ...samplePage([]), total: 0, chart_points: [], outliers: [] });
  renderWithLocale(<SpeakingBenchmarkReports />);
  expect(await screen.findByRole("heading", { name: "No paired scores yet" })).toBeVisible();
  expect(screen.getByRole("link", { name: "Open recordings" })).toHaveAttribute("href", "/admin/speaking-benchmark");
  expect(screen.queryByRole("img", { name: "Score distribution" })).not.toBeInTheDocument();
  for (const table of screen.queryAllByRole("table")) expect(table).not.toBeVisible();
  expect(screen.getByText("Paired Overall scores").nextElementSibling).toHaveTextContent("0");
  expect(screen.getByText("AI prediction coverage").nextElementSibling).toHaveTextContent("—");
  expect(screen.getByRole("link", { name: "Export filtered CSV" })).toBeInTheDocument();
});

it("asks for one compatible configuration before showing metrics or exports", async () => {
  vi.mocked(api.reportSummary).mockResolvedValue({ ...filledReport, requires_configuration: true });
  renderWithLocale(<SpeakingBenchmarkReports />);
  expect(await screen.findByText(en["speakingReport.chooseConfig"])).toBeVisible();
  expect(screen.queryByRole("heading", { name: "No paired scores yet" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Export filtered CSV" })).not.toBeInTheDocument();
  expect(screen.queryByRole("img", { name: "Score distribution" })).not.toBeInTheDocument();
});

it("keeps per-criterion human coverage visible when every AI prediction is still missing", async () => {
  vi.mocked(api.reportSummary).mockResolvedValue({ ...filledReport, criteria: Object.fromEntries(Object.entries(filledReport.criteria).map(([key, metric]) => [key, { ...metric, count: 0, coverage_rate: 0, mae: null, signed_bias: null, within_0_5: null }])) });
  vi.mocked(api.reportSamples).mockResolvedValue({ ...samplePage(), chart_points: reportComparisons.map(row => ({ ...row, ai: { overall: null } })) });
  renderWithLocale(<SpeakingBenchmarkReports />);
  const metrics = await screen.findByRole("table", { name: en["speakingReport.errors"] });
  const overall = within(metrics).getByRole("row", { name: /Overall score/ });
  expect(overall).toHaveTextContent("0 / 24");
  expect(overall).toHaveTextContent("—");
  expect(screen.getByText("AI prediction coverage", { selector: "dt" }).nextElementSibling).toHaveTextContent("0.0%");
});

it("keeps every advanced statistic and global outlier accessible without crowding the main table", async () => {
  renderWithLocale(<SpeakingBenchmarkReports />);
  const metrics = await screen.findByRole("table", { name: en["speakingReport.errors"] });
  expect(within(metrics).getAllByRole("columnheader")).toHaveLength(5);
  expect(screen.getByRole("table", { name: "Advanced statistics" })).not.toBeVisible();
  fireEvent.click(screen.getByText("Advanced statistics", { selector: "summary" }));
  const advanced = screen.getByRole("table", { name: "Advanced statistics" });
  expect(within(advanced).getByRole("columnheader", { name: "Larger-error measure (RMSE)" })).toBeVisible();
  expect(within(advanced).getByRole("columnheader", { name: "Weighted kappa" })).toBeVisible();
  fireEvent.click(screen.getByText(/Recordings with the largest differences/, { selector: "summary" }));
  expect(screen.getByRole("link", { name: "SYNTH-005" })).toHaveAttribute("href", `/admin/speaking-benchmark/${reportComparisons[4].sample_id}`);
});

it("preserves filter drafts through disclosure and locale changes, then uses the applied values for exports", async () => {
  renderWithLocale(<SpeakingBenchmarkReports />);
  await screen.findByRole("table", { name: en["speakingReport.errors"] });
  const more = screen.getByText("More filters", { selector: "summary" });
  fireEvent.click(more);
  fireEvent.change(screen.getByLabelText("Model"), { target: { value: "fictional-model" } });
  fireEvent.change(screen.getByLabelText("Uploaded from"), { target: { value: "2026-11-01T12:00" } });
  fireEvent.click(more);
  fireEvent.click(more);
  expect(screen.getByLabelText("Model")).toHaveValue("fictional-model");
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  expect(screen.getByLabelText("Mô hình")).toHaveValue("fictional-model");
  expect(screen.getByRole("link", { name: "Xuất theo bộ lọc CSV" }).getAttribute("href")).not.toContain("fictional-model");
  fireEvent.click(screen.getByRole("button", { name: "Áp dụng bộ lọc" }));
  await waitFor(() => expect(api.reportSummary).toHaveBeenLastCalledWith(expect.objectContaining({ model: "fictional-model", uploaded_from: new Date("2026-11-01T12:00").toISOString() })));
  expect(await screen.findByRole("link", { name: "Xuất theo bộ lọc CSV" })).toHaveAttribute("href", expect.stringContaining("model=fictional-model"));
  fireEvent.click(screen.getByRole("button", { name: "Đặt lại bộ lọc" }));
  await waitFor(() => expect(api.reportSummary).toHaveBeenLastCalledWith({ verified_only: "true" }));
  expect(screen.getByLabelText("Mô hình")).toHaveValue("");
});

it("retains the last successful report and its export filters when a new filter request fails", async () => {
  renderWithLocale(<SpeakingBenchmarkReports />);
  await screen.findByRole("table", { name: en["speakingReport.errors"] });
  fireEvent.click(screen.getByText("More filters", { selector: "summary" }));
  fireEvent.change(screen.getByLabelText("Model"), { target: { value: "unavailable-model" } });
  let reject!: (reason: Error) => void;
  vi.mocked(api.reportSummary).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
  expect(screen.getByRole("status")).toHaveTextContent("previous results remain visible");
  expect(screen.queryByRole("link", { name: "Export filtered CSV" })).not.toBeInTheDocument();
  reject(new Error("SYNTHETIC_REPORT_UNAVAILABLE"));
  expect(await screen.findByRole("alert")).toHaveTextContent(en["speakingReport.loadFailed"]);
  expect(screen.getByText(en["speakingReport.keptResults"])).toBeVisible();
  expect(screen.getByRole("link", { name: "Export filtered CSV" }).getAttribute("href")).not.toContain("unavailable-model");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(await screen.findByRole("link", { name: "Export filtered CSV" })).toHaveAttribute("href", expect.stringContaining("model=unavailable-model"));
});

it("can request the next page again after that page failed without getting stuck loading", async () => {
  vi.mocked(api.reportSamples).mockResolvedValue({ ...samplePage(), total: 60 });
  renderWithLocale(<SpeakingBenchmarkReports />);
  await screen.findByRole("table", { name: en["speakingReport.errors"] });
  vi.mocked(api.reportSamples).mockRejectedValueOnce(new Error("SYNTHETIC_PAGE_UNAVAILABLE"));
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("alert");
  expect(screen.getByText("Showing 1–2 of 60 recordings")).toBeVisible();
  vi.mocked(api.reportSamples).mockResolvedValue({ ...samplePage([reportComparisons[2]]), total: 60, offset: 25 });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(api.reportSamples).toHaveBeenCalledTimes(3));
  expect(await screen.findByText("Showing 26–26 of 60 recordings")).toBeVisible();
  expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("keeps genuine zero scores, switches chart questions and offers exact tabular values", () => {
  renderWithLocale(<ReportCharts rows={[{ ...comparison, human: { overall: 0 }, ai: { overall: 0 } }]} />);
  expect(screen.getByRole("img", { name: "Score distribution" })).toBeVisible();
  fireEvent.click(screen.getByText("View the values behind this chart", { selector: "summary" }));
  const table = screen.getByRole("table", { name: "Score distribution" });
  expect(within(table).getByRole("row", { name: "0 1 1" })).toBeVisible();
  fireEvent.click(screen.getByRole("radio", { name: "Compare individual scores" }));
  expect(screen.getByRole("img", { name: "Compare individual scores" })).toBeVisible();
  expect(screen.queryByRole("img", { name: "Score distribution" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: "Direction of the differences" }));
  expect(screen.getByRole("img", { name: "Direction of the differences" })).toBeVisible();
});

it("does not draw fake paired charts when only a verified human score exists", () => {
  renderWithLocale(<ReportCharts rows={[{ ...comparison, ai: { overall: null } }]} />);
  fireEvent.click(screen.getByRole("radio", { name: "Compare individual scores" }));
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText(en["speakingReport.noPairedChart"])).toBeVisible();
});

it.each(["workflow", "reports", "reviewer"] as const)("provides a complete natural-language %s guide in English and Vietnamese", mode => {
  renderWithLocale(<LabGuide mode={mode} />);
  fireEvent.click(document.querySelector("[data-speaking-guide] > summary")!);
  const table = screen.getByRole("table");
  expect(within(table).getAllByRole("rowheader").length).toBe(mode === "workflow" ? 6 : mode === "reports" ? 5 : 3);
  fireEvent.click(screen.getByRole("button", { name: "Switch to Vietnamese" }));
  expect(screen.getByRole("table")).toBe(table);
  expect(within(table).getByRole("columnheader", { name: "Cách thực hiện" })).toBeVisible();
  const key = mode === "workflow" ? "speakingGuide.prepare" : mode === "reports" ? "speakingGuide.filter" : "speakingGuide.listen";
  expect(screen.getByText(vietnamese[key])).toBeVisible();
});
