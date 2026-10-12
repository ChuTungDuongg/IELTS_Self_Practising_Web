import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LibraryVersionContent } from "@/features/practice/library-content";
import { apiRequest } from "@/lib/api/client";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";
import { renderWithLocale } from "./locale-test-utils";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/client", async (original) => ({
  ...await original<typeof import("@/lib/api/client")>(),
  apiRequest: vi.fn(),
}));

const id = (digit: number) => `${digit}${"1".repeat(7)}-1111-4111-8111-${"1".repeat(12)}`;
const published = {
  id: id(1), version_number: 13, status: "PUBLISHED" as const,
  created_at: "2026-10-12T00:00:00Z", published_at: "2026-10-12T00:00:00Z",
};
const test: TestSummary = {
  id: id(2), title: "Fictional four-skill practice", origin: "ADMIN",
  description: "A fictional authored description.", source_label: null,
  test_number: 1, archived_at: null, created_at: published.created_at,
  updated_at: published.created_at, versions: [published],
};
const baseModule = {
  title: null, recommended_duration_seconds: 3600, passage_count: 0,
  listening_part_count: 0, writing_task_count: 0, question_count: 0,
};
const version: VersionDetail = {
  ...published, test_id: test.id, test_title: test.title,
  modules: [
    {
      ...baseModule, id: id(3), module_type: "READING", passage_count: 1, question_count: 40,
      reading_passages: [{ id: id(7), title: "Fictional river history", order_index: 0,
        question_groups: [{ question_type: "matching", start_number: 1, end_number: 4, question_count: 4 }] }],
    },
    {
      ...baseModule, id: id(4), module_type: "LISTENING", listening_part_count: 1, question_count: 40,
      listening_sections: [{ id: id(8), title: "Fictional town tour", order_index: 0,
        question_groups: [{ question_type: "note_completion", start_number: 1, end_number: 10, question_count: 10 }] }],
    },
    {
      ...baseModule, id: id(5), module_type: "WRITING", writing_task_count: 1,
      writing_tasks: [{ id: id(9), task_number: 1, task_type: "PIE_CHART",
        minimum_recommended_words: 150, recommended_duration_seconds: 1200,
        prompt_excerpt: "Describe fictional population charts." }],
    },
    {
      ...baseModule, id: id(6), module_type: "SPEAKING", recommended_duration_seconds: 900, question_count: 1,
      speaking_parts: [{ id: id(7), part_number: 1, order_index: 0, title: "Fictional interview",
        prompts: [{ id: id(8), order_index: 0, prompt_type: "SHORT_ANSWER", prompt_text: "Describe your fictional town.", cue_points: [] }] }],
    },
  ],
};
const startedAttempt = {
  attempt_id: id(9), test_version_id: version.id, test_session_id: id(8),
  attempt_context: "FULL_MOCK", module: "LISTENING", status: "IN_PROGRESS",
  finished_reason: null, timer_mode: "COUNTDOWN", timer_limit_seconds: 3600,
  started_at: published.created_at, paused_at: null, total_paused_seconds: 0,
  deadline_at: "2026-10-12T01:00:00Z", last_active_at: published.created_at,
  finished_at: null, elapsed_seconds: 0, remaining_seconds: 3600,
  raw_score: null, max_score: null, band_score: null, server_time: published.created_at,
};
const started = {
  current_attempt: startedAttempt,
  session: {
    session_id: id(8), test_version_id: version.id, test_title: test.title,
    version_number: 13, status: "IN_PROGRESS", started_at: published.created_at,
    finished_at: null, current_module: "LISTENING", next_module: "READING",
    current_attempt: startedAttempt, module_order: ["LISTENING", "READING", "WRITING", "SPEAKING"],
    attempts: [], warnings: [], overall_band_score: null,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("Test Library detail hierarchy", () => {
  it("keeps the application banner unique when the detail is rendered inside main", () => {
    renderWithLocale(<><header>BandPilot</header><main><LibraryVersionContent test={test} version={version} /></main></>);
    expect(screen.getAllByRole("banner")).toHaveLength(1);
  });
  it.each([
    { locale: "en", origin: "ADMIN", owner: null, attribution: "Official", metadata: "Published · Version 13", back: "Back to practice library" },
    { locale: "en", origin: "TEACHER", owner: "Fictional Teacher", attribution: "Community · contributed by Fictional Teacher", metadata: "Published · Version 13", back: "Back to practice library" },
    { locale: "vi", origin: "ADMIN", owner: null, attribution: "Chính thức", metadata: "Đã xuất bản · Phiên bản 13", back: "Quay lại thư viện luyện tập" },
    { locale: "vi", origin: "TEACHER", owner: "Fictional Teacher", attribution: "Cộng đồng · đóng góp bởi Fictional Teacher", metadata: "Đã xuất bản · Phiên bản 13", back: "Quay lại thư viện luyện tập" },
  ] as const)("groups $locale $origin attribution and version under one primary identity", ({ locale, origin, owner, attribution, metadata, back }) => {
    const view = renderWithLocale(<LibraryVersionContent test={{ ...test, origin, owner_display_name: owner }} version={version} />);
    if (locale === "vi") fireEvent.click(screen.getByText("Switch to Vietnamese"));
    const title = screen.getByRole("heading", { level: 1, name: test.title });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const header = title.closest(".practice-detail-header")!;
    expect(header).not.toBeNull();
    expect(within(header as HTMLElement).getByRole("link", { name: `← ${back}` })).toHaveAttribute("href", "/library");
    const meta = header.querySelector(".practice-detail-meta")!;
    expect(meta).not.toBeNull();
    expect(within(meta as HTMLElement).getByText(metadata)).toHaveClass("status-badge", "status-published");
    const originLabel = within(meta as HTMLElement).getByText(attribution);
    expect(originLabel.tagName).toBe("SPAN");
    expect(screen.getAllByText(attribution)).toHaveLength(1);
    expect(view.container.querySelector("p.practice-module-kicker")).not.toHaveTextContent(attribution);
    expect(within(header as HTMLElement).getByText(test.description!)).toBeInTheDocument();
    expect(view.container.textContent).not.toMatch(/pages\.library\.|library\.(?:official|community)|practice\.mock/);
  });

  it.each([
    { locale: "en", sequence: "Listening → Reading → Writing → Speaking", helper: "Uses the configured module timings.", action: "Start Full Mock" },
    { locale: "vi", sequence: "Nghe → Đọc → Viết → Nói", helper: "Sử dụng thời gian đã cấu hình cho từng kỹ năng.", action: "Bắt đầu bài thi thử" },
  ])("keeps the $locale four-skill sequence and action in a compact strip", ({ locale, sequence, helper, action }) => {
    renderWithLocale(<LibraryVersionContent test={test} version={version} />);
    if (locale === "vi") fireEvent.click(screen.getByText("Switch to Vietnamese"));
    const order = screen.getByRole("heading", { name: sequence });
    const strip = order.closest(".practice-full-mock-strip")!;
    expect(strip).not.toBeNull();
    expect(within(strip as HTMLElement).getByText(helper)).toBeInTheDocument();
    const button = within(strip as HTMLElement).getByRole("button", { name: action });
    expect(button).toBeEnabled();
    expect(button.closest(".practice-full-mock-action")).not.toBeNull();
  });

  it("retains the four skill cards, their content, metadata, and Speaking disclosure", () => {
    const view = renderWithLocale(<LibraryVersionContent test={test} version={version} />);
    const cards = [...view.container.querySelectorAll<HTMLElement>(".practice-skill-grid > article")];
    expect(cards).toHaveLength(4);
    expect(cards.map((card) => within(card).getByRole("heading", { level: 2 }).textContent)).toEqual(["Reading", "Listening", "Writing", "Speaking"]);
    for (const card of cards) {
      expect(within(card).getByText("Continue with this skill in the published, frozen test version.")).toBeInTheDocument();
      expect(within(card).getByText("Version").closest("dl")).toHaveTextContent("Version13");
    }
    expect(within(cards[0]).getByText("Fictional river history")).toBeInTheDocument();
    expect(within(cards[0]).getByText("Matching")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Fictional town tour")).toBeInTheDocument();
    expect(within(cards[1]).getByText("Note Completion")).toBeInTheDocument();
    expect(within(cards[2]).getByText("Describe fictional population charts.")).toBeInTheDocument();
    expect(within(cards[2]).getByText("Pie chart")).toBeInTheDocument();
    expect(within(cards[3]).getByText("Fictional interview")).toBeInTheDocument();
    const question = within(cards[3]).getByText("Describe your fictional town.");
    expect(question).not.toBeVisible();
    fireEvent.click(within(cards[3]).getByText("View questions"));
    expect(question).toBeVisible();
    expect(within(cards[3]).getByRole("button", { name: "Start Speaking" })).toBeEnabled();
  });

  it("starts the existing Full Mock session once and follows the returned attempt route", async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(apiRequest).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    renderWithLocale(<LibraryVersionContent test={test} version={version} />);
    fireEvent.click(screen.getByRole("button", { name: "Start Full Mock" }));
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("button", { name: "Đang bắt đầu…" })).toBeDisabled();
    expect(apiRequest).toHaveBeenCalledExactlyOnceWith("/test-sessions", {
      method: "POST", body: JSON.stringify({ test_version_id: version.id }),
    });
    await act(async () => finish(started));
    await waitFor(() => expect(push).toHaveBeenCalledExactlyOnceWith(`/attempt/${startedAttempt.attempt_id}`));
  });

  it.each([
    { locale: "en", warning: "Reading has 39 questions. An official band will not be calculated.", unavailable: "Full Mock unavailable: Speaking recommended duration is missing.", action: "Start Full Mock" },
    { locale: "vi", warning: "Đọc có 39 câu hỏi. Không tính điểm band chính thức.", unavailable: "Không thể làm bài thi thử: Thiếu thời gian đề xuất cho Nói.", action: "Bắt đầu bài thi thử" },
  ])("preserves $locale readiness warnings and unavailable state", ({ locale, warning, unavailable, action }) => {
    renderWithLocale(<LibraryVersionContent test={test} version={{ ...version, modules: version.modules.map((module) => module.module_type === "READING" ? { ...module, question_count: 39 } : module.module_type === "SPEAKING" ? { ...module, recommended_duration_seconds: null } : module) }} />);
    if (locale === "vi") fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByText(warning)).toBeInTheDocument();
    expect(screen.getByText(unavailable)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: action })).not.toBeInTheDocument();
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it.each([
    { locale: "en", action: "Start Full Mock", error: "Could not start the Full Mock." },
    { locale: "vi", action: "Bắt đầu bài thi thử", error: "Không thể bắt đầu bài thi thử." },
  ])("preserves the $locale retry action after a Full Mock request error", async ({ locale, action, error }) => {
    vi.mocked(apiRequest).mockRejectedValue(new Error("Unavailable fictional service"));
    renderWithLocale(<LibraryVersionContent test={test} version={version} />);
    if (locale === "vi") fireEvent.click(screen.getByText("Switch to Vietnamese"));
    fireEvent.click(screen.getByRole("button", { name: action }));
    expect(await screen.findByRole("alert")).toHaveTextContent(error);
    expect(screen.getByRole("button", { name: action })).toBeEnabled();
    expect(push).not.toHaveBeenCalled();
  });
});
