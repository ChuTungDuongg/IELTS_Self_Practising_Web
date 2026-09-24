import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TestLibraryList } from "@/features/test-builder/test-library-list";
import { AppShell } from "@/components/ui/app-shell";
import TestDetailPage from "@/app/admin/tests/[testId]/page";
import { parseBuilderVersion } from "@/lib/api/builder";
import type { TestSummary } from "@/lib/api/schema";
import { getTest } from "@/lib/api/tests";
import { BUILDER_EDIT_ROUTE, builderEditPath } from "@/lib/routes";

vi.mock("next/navigation", () => ({ usePathname: () => "/", useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/features/auth/auth-provider", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/auth/auth-provider")>();
  return { ...actual, useAuth: () => ({ user: { role: "ADMIN", display_name: "Fictional admin" }, loading: false, sessionError: null, logout: vi.fn() }) };
});
vi.mock("@/lib/api/tests", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/tests")>();
  return { ...actual, getTest: vi.fn() };
});

const testId = "11111111-1111-4111-8111-111111111111";
const versionId = "22222222-2222-4222-8222-222222222222";
const draft: TestSummary = {
  id: testId,
  title: "Fictional draft",
  description: null,
  source_label: null,
  test_number: null,
  archived_at: null,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
  versions: [{ id: versionId, version_number: 1, status: "DRAFT", created_at: "2026-09-19T00:00:00Z", published_at: null }],
};

describe("canonical Builder edit route", () => {
  it("exists in the App Router and is used by Continue draft", () => {
    expect(existsSync(resolve(process.cwd(), "src/app/admin/tests/page.tsx"))).toBe(true);
    expect(BUILDER_EDIT_ROUTE).toBe("/admin/tests/[testId]/versions/[versionId]/edit");
    expect(existsSync(resolve(process.cwd(), "src/app/admin/tests/[testId]/versions/[versionId]/edit/page.tsx"))).toBe(true);
    render(<TestLibraryList activeTests={[draft]} archivedTests={[]} />);
    expect(screen.getByRole("link", { name: /Continue draft/ })).toHaveAttribute("href", builderEditPath(testId, versionId));
  });

  it("keeps the sidebar Builder destination on the authoring Test Library", () => {
    render(<AppShell><p>content</p></AppShell>);
    expect(screen.getByRole("link", { name: "Builder" })).toHaveAttribute("href", "/admin/tests");
  });

  it("uses the same route from the test detail version list", async () => {
    vi.mocked(getTest).mockResolvedValue(draft);
    render(await TestDetailPage({ params: Promise.resolve({ testId }) }));
    expect(screen.getByRole("link", { name: /Version 1/ })).toHaveAttribute("href", builderEditPath(testId, versionId));
    expect(screen.getByText("Created 19/09/2026, 07:00:00")).toBeInTheDocument();
  });

  it("accepts a Reading-only Builder payload without Listening arrays", () => {
    const parsed = parseBuilderVersion({
      id: versionId,
      test_id: testId,
      test_title: "Fictional draft",
      version_number: 1,
      status: "DRAFT",
      modules: [{
        id: "33333333-3333-4333-8333-333333333333",
        revision: 1,
        module_type: "READING",
        title: "Reading",
        recommended_duration_seconds: 3600,
      }],
    });
    expect(parsed.modules[0].passages).toEqual([]);
    expect(parsed.modules[0].listening_parts).toEqual([]);
    expect(parsed.modules[0].audio_asset).toBeNull();
  });

  it("round-trips YNNG and one shared Listening audio in the Builder DTO", () => {
    const audio = { id: "44444444-4444-4444-8444-444444444444", original_name: "shared.mp3", mime_type: "audio/mpeg", file_size: 123, content_url: "/assets/shared/content" };
    const parsed = parseBuilderVersion({
      id: versionId,
      test_id: testId,
      test_title: "Fictional draft",
      version_number: 1,
      status: "DRAFT",
      modules: [{
        id: "33333333-3333-4333-8333-333333333333",
        revision: 1,
        module_type: "LISTENING",
        title: "Listening",
        recommended_duration_seconds: 1800,
        audio_asset: audio,
        passages: [],
        listening_parts: [{ id: "55555555-5555-4555-8555-555555555555", revision: 1, title: "Section 1", order_index: 0, question_groups: [{ id: "66666666-6666-4666-8666-666666666666", revision: 1, question_type: "yes_no_not_given", instruction: "", config: {}, order_index: 0, questions: [{ id: "77777777-7777-4777-8777-777777777777", number: 1, prompt: "Claim", config: {}, answer_key: { kind: "SINGLE_OPTION", value: "YES" }, explanation: null, order_index: 0 }] }] }],
      }],
    });
    expect(parsed.modules[0].audio_asset?.id).toBe(audio.id);
    expect(parsed.modules[0].listening_parts[0].question_groups[0].question_type).toBe("yes_no_not_given");
  });
});
