import { screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { renderWithLocale } from "./locale-test-utils";
import { LibraryContent, LibraryVersionContent } from "@/features/practice/library-content";
import { SkillPractice } from "@/features/practice/skill-practice";
import { selectedPublishedVersion } from "@/lib/published-version";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
const old: VersionDetail = { id: "old", test_id: "test", test_title: "Fictional test", version_number: 1, status: "PUBLISHED", created_at: "now", published_at: "now", modules: [{ id: "module", module_type: "READING", title: null, recommended_duration_seconds: 3600, passage_count: 1, listening_part_count: 0, writing_task_count: 0, question_count: 1, reading_passages: [{ id: "passage", title: "Fictional passage", order_index: 0, question_groups: [] }] }] };
const latest: VersionDetail = { ...old, id: "latest", version_number: 3 };
const test: TestSummary = { id: "test", title: "Fictional test", description: null, source_label: null, test_number: null, archived_at: null, created_at: "now", updated_at: "now", versions: [latest, old] };
beforeEach(() => localStorage.clear());
it("groups authorized library revisions by logical Test and links the selected published version", () => {
  renderWithLocale(<LibraryContent items={[{ test, version: old, detail: old }, { test, version: latest, detail: latest }]} />);
  expect(screen.getAllByRole("heading", { name: test.title })).toHaveLength(1);
  expect(screen.queryByText(/Version\s+\d/i)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Open test/ })).toHaveAttribute("href", "/library/latest");
});
it("keeps an explicitly selected frozen detail version without displaying its technical number", () => {
  renderWithLocale(<LibraryVersionContent test={test} version={old} />);
  expect(screen.queryByText(/Version\s+\d|Published · Version/i)).not.toBeInTheDocument();
  expect(screen.queryByText("Version")).not.toBeInTheDocument();
});
it("does not duplicate focused discovery units from older eligible versions", () => {
  renderWithLocale(<SkillPractice versions={[old, latest]} />);
  expect(screen.queryByText(/Version\s+\d/i)).not.toBeInTheDocument();
  expect(screen.getAllByText("Fictional passage")).toHaveLength(1);
});
it("never chooses a newer draft or archived revision over an eligible published snapshot", () => {
  expect(selectedPublishedVersion([old, { ...latest, status: "DRAFT" }, { ...latest, status: "ARCHIVED", version_number: 8 }])?.id).toBe("old");
});
