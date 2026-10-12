import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import postcss from "postcss";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SpeakingBuilder } from "@/features/test-builder/speaking-builder";
import { BuilderLifecycleProvider, BuilderAutosaveStatus } from "@/features/test-builder/builder-lifecycle";
import { BuilderWorkspaceNavigation } from "@/features/test-builder/builder-workspace-navigation";
import { BuilderEditorPage } from "@/features/test-builder/builder-editor-page";
import { builderContentSummary } from "@/features/test-builder/content-summary";
import { ModerationPreview } from "@/features/classrooms/moderation-preview";
import * as api from "@/lib/api/builder";
import { getVersionModeration } from "@/lib/api/content-governance";
import { renderWithLocale } from "./locale-test-utils";

const navigation = vi.hoisted(() => ({ refresh: vi.fn(), push: vi.fn(), notFound: vi.fn(), redirect: vi.fn() }));
vi.mock("next/navigation", () => ({ ...navigation, useRouter: () => navigation }));
vi.mock("@/lib/api/builder", async (original) => ({
  ...await original<typeof import("@/lib/api/builder")>(),
  createSpeakingModule: vi.fn(), createSpeakingPrompt: vi.fn(), updateSpeakingPart: vi.fn(),
  reorderSpeakingPrompts: vi.fn(), deleteSpeakingPrompt: vi.fn(), getBuilderVersion: vi.fn(),
}));
vi.mock("@/lib/api/content-governance", async (original) => ({
  ...await original<typeof import("@/lib/api/content-governance")>(), getVersionModeration: vi.fn(),
}));

const versionId = "11111111-1111-4111-8111-111111111111";
const testId = "22222222-2222-4222-8222-222222222222";
function version(withModule = true): api.BuilderVersion {
  return api.parseBuilderVersion({ id: versionId, test_id: testId, test_title: "Fictional Speaking draft", version_number: 1, status: "DRAFT", modules: withModule ? [{
    id: "33333333-3333-4333-8333-333333333333", revision: 1, module_type: "SPEAKING", title: "Speaking", recommended_duration_seconds: null,
    speaking_parts: [1, 2, 3].map(number => ({ id: `44444444-4444-4444-8444-44444444444${number}`, revision: 1, part_number: number, order_index: number - 1, title: null, instructions: null,
      prompts: number === 2 ? [{ id: "55555555-5555-4555-8555-555555555555", prompt_type: "LONG_TURN", prompt_text: "Describe a fictional tool.", preparation_seconds: 60, response_seconds: 120, order_index: 0, config_json: { cue_points: ["Its purpose"] } }] : [],
    })),
  }] : [] });
}

function renderBuilder(value = version(), editable = true) {
  return render(<BuilderLifecycleProvider><BuilderAutosaveStatus /><SpeakingBuilder version={value} editable={editable} /></BuilderLifecycleProvider>);
}

describe("P1 Speaking Builder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(getVersionModeration).mockResolvedValue([]);
    vi.mocked(api.createSpeakingModule).mockImplementation(async () => version().modules[0]);
    vi.mocked(api.createSpeakingPrompt).mockImplementation(async (partId, body) => {
      const part = version().modules[0].speaking_parts!.find(item => item.id === partId)!;
      return { ...part, revision: body.expected_revision + 1, prompts: [...part.prompts, { id: crypto.randomUUID(), order_index: part.prompts.length, prompt_type: body.prompt_type, prompt_text: "", preparation_seconds: body.prompt_type === "LONG_TURN" ? 60 : 0, response_seconds: body.prompt_type === "LONG_TURN" ? 120 : 60, config_json: { cue_points: [] } }] };
    });
    vi.mocked(api.updateSpeakingPart).mockImplementation(async (partId, body) => {
      const part = version().modules[0].speaking_parts!.find(item => item.id === partId)!;
      return { ...part, ...body, revision: body.expected_revision + 1 };
    });
  });

  it("keeps Speaking navigable before creation and localizes the same link", () => {
    renderWithLocale(<BuilderWorkspaceNavigation testId={testId} versionId={versionId} workspace="speaking" />);
    const link = screen.getByRole("link", { name: /SpeakingNot created/ });
    expect(link).toHaveAttribute("href", expect.stringContaining("workspace=speaking"));
    expect(link).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByText("Switch to Vietnamese"));
    expect(screen.getByRole("link", { name: /NóiChưa tạo/ })).toBe(link);
  });

  it("creates the module and shows three parts without waiting for refreshed props", async () => {
    renderBuilder(version(false));
    fireEvent.click(screen.getByRole("button", { name: "Create Speaking module" }));
    await waitFor(() => expect(api.createSpeakingModule).toHaveBeenCalledWith(versionId));
    expect(await screen.findByRole("group", { name: "Speaking Part 1" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Speaking Part 3" })).toBeInTheDocument();
  });

  it.each([1, 3])("appends in Part %s with a 60 second default and focuses its prompt", async number => {
    renderBuilder();
    const part = screen.getByRole("group", { name: `Speaking Part ${number}` });
    fireEvent.click(within(part).getByRole("button", { name: "Add question" }));
    const prompt = await within(part).findByRole("textbox", { name: "Prompt 1" });
    expect(prompt).toHaveFocus();
    expect(within(part).getByRole("spinbutton", { name: "Response time (seconds)" })).toHaveValue(60);
    expect(api.createSpeakingPrompt).toHaveBeenCalledWith(expect.any(String), { expected_revision: 1, prompt_type: "SHORT_ANSWER" });
  });

  it("focuses newly created module authoring content", async () => {
    renderBuilder(version(false));
    fireEvent.click(screen.getByRole("button", { name: "Create Speaking module" }));
    const part = await screen.findByRole("group", { name: "Speaking Part 1" });
    expect(within(part).getByRole("textbox", { name: "Part title" })).toHaveFocus();
  });

  it("hydrates a newer clean server revision without resaving unchanged content", async () => {
    const value = version();
    const view = renderBuilder(value);
    const next = structuredClone(value);
    next.modules[0].speaking_parts![1].revision = 2;
    next.modules[0].speaking_parts![1].prompts[0].prompt_text = "Updated fictional tool.";
    view.rerender(<BuilderLifecycleProvider><BuilderAutosaveStatus /><SpeakingBuilder version={next} /></BuilderLifecycleProvider>);
    expect(screen.getByRole("textbox", { name: "Cue-card prompt" })).toHaveValue("Updated fictional tool.");
    const save = screen.queryByRole("button", { name: "Save now" });
    if (save) fireEvent.click(save);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
    expect(api.updateSpeakingPart).not.toHaveBeenCalled();
  });

  it.each([false, true])("reorders immediately and honors reduced motion=%s", async reduced => {
    const value = version();
    const part = value.modules[0].speaking_parts![0];
    part.prompts = ["First", "Second"].map((text, index) => ({ id: crypto.randomUUID(), order_index: index, prompt_type: "SHORT_ANSWER", prompt_text: text, response_seconds: 60, preparation_seconds: 0, config_json: { cue_points: [] } }));
    let moved = false;
    const rectangle = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function(this: HTMLElement) {
      const isFirst = this.dataset.promptId === part.prompts[0].id;
      return new DOMRect(0, isFirst === !moved ? 0 : 100, 100, 20);
    });
    const animate = vi.fn();
    const previousAnimation = HTMLElement.prototype.animate;
    HTMLElement.prototype.animate = animate;
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: reduced })));
    vi.mocked(api.reorderSpeakingPrompts).mockImplementation(async () => {
      moved = true;
      return { ...part, revision: 2, prompts: [...part.prompts].reverse().map((prompt, order_index) => ({ ...prompt, order_index })) };
    });
    try {
      renderBuilder(value);
      const group = screen.getByRole("group", { name: "Speaking Part 1" });
      fireEvent.click(within(group).getAllByRole("button", { name: "Move down" })[0]);
      await waitFor(() => expect(within(group).getByRole("textbox", { name: "Prompt 1" })).toHaveValue("Second"));
      if (reduced) expect(animate).not.toHaveBeenCalled();
      else expect(animate).toHaveBeenCalledWith(expect.any(Array), { duration: 180, easing: "ease-out" });
    } finally {
      rectangle.mockRestore();
      HTMLElement.prototype.animate = previousAnimation;
      vi.unstubAllGlobals();
    }
  });

  it("renders distinct Part 2 timers, cue points and candidate preview", () => {
    renderBuilder();
    const part = screen.getByRole("group", { name: "Speaking Part 2" });
    expect(within(part).getByRole("spinbutton", { name: "Preparation time (seconds)" })).toHaveValue(60);
    expect(within(part).getByRole("spinbutton", { name: "Response time (seconds)" })).toHaveValue(120);
    expect(within(part).getByRole("textbox", { name: "Cue points" })).toHaveValue("Its purpose");
    expect(within(part).getByRole("region", { name: "Candidate preview" })).toHaveTextContent("Describe a fictional tool.");
  });

  it("autosaves cue points and configurable timers through the existing revision lifecycle", async () => {
    renderBuilder();
    const part = screen.getByRole("group", { name: "Speaking Part 2" });
    fireEvent.change(within(part).getByRole("textbox", { name: "Cue points" }), { target: { value: "Its purpose\nWhy it helps" } });
    fireEvent.change(within(part).getByRole("spinbutton", { name: "Response time (seconds)" }), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Save now" }));
    await waitFor(() => expect(api.updateSpeakingPart).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ expected_revision: 1, prompts: [expect.objectContaining({ id: "55555555-5555-4555-8555-555555555555", response_seconds: 100, config_json: { cue_points: ["Its purpose", "Why it helps"] } })] })));
    expect(within(part).getByRole("region", { name: "Candidate preview" })).toHaveTextContent("Why it helps");
  });

  it("reorders stable prompt IDs and retains current prompt text", async () => {
    const value = version();
    const part = value.modules[0].speaking_parts![0];
    part.prompts = ["First fictional question", "Second fictional question"].map((text, index) => ({ id: crypto.randomUUID(), order_index: index, prompt_type: "SHORT_ANSWER", prompt_text: text, response_seconds: 60, preparation_seconds: 0, config_json: { cue_points: [] } }));
    vi.mocked(api.reorderSpeakingPrompts).mockResolvedValue({ ...part, revision: 2, prompts: [...part.prompts].reverse().map((prompt, index) => ({ ...prompt, order_index: index })) });
    renderBuilder(value);
    const group = screen.getByRole("group", { name: "Speaking Part 1" });
    fireEvent.click(within(group).getAllByRole("button", { name: "Move down" })[0]);
    await waitFor(() => expect(api.reorderSpeakingPrompts).toHaveBeenCalledWith(part.id, 1, [part.prompts[1].id, part.prompts[0].id]));
    expect(within(group).getByRole("textbox", { name: "Prompt 1" })).toHaveValue("Second fictional question");
  });

  it("appends optional follow-ups after the long turn", async () => {
    renderBuilder();
    const part = screen.getByRole("group", { name: "Speaking Part 2" });
    fireEvent.click(within(part).getByRole("button", { name: "Add follow-up" }));
    expect(await within(part).findByRole("textbox", { name: "Prompt 2" })).toHaveFocus();
    expect(api.createSpeakingPrompt).toHaveBeenCalledWith(expect.any(String), { expected_revision: 1, prompt_type: "FOLLOW_UP" });
  });

  it("deletes a draft prompt and uses the returned normalized order", async () => {
    const value = version();
    const part = value.modules[0].speaking_parts![0];
    part.prompts = [{ ...value.modules[0].speaking_parts![1].prompts[0], id: crypto.randomUUID(), prompt_type: "SHORT_ANSWER", preparation_seconds: 0, response_seconds: 60, config_json: { cue_points: [] } }];
    vi.mocked(api.deleteSpeakingPrompt).mockResolvedValue({ ...part, revision: 2, prompts: [] });
    renderBuilder(value);
    fireEvent.click(within(screen.getByRole("group", { name: "Speaking Part 1" })).getByRole("button", { name: "Delete question" }));
    await waitFor(() => expect(api.deleteSpeakingPrompt).toHaveBeenCalledWith(part.id, part.prompts[0].id, 1));
    expect(within(screen.getByRole("group", { name: "Speaking Part 1" })).queryByRole("textbox", { name: "Prompt 1" })).not.toBeInTheDocument();
  });

  it("keeps frozen content non-editable without autosave or mutations", async () => {
    const value = version(); value.status = "PUBLISHED";
    renderBuilder(value, false);
    expect(screen.getByRole("textbox", { name: "Cue-card prompt" })).toBeDisabled();
    for (const button of screen.getAllByRole("button", { name: "Add question" })) expect(button).toBeDisabled();
    expect(api.updateSpeakingPart).not.toHaveBeenCalled();
  });

  it("marks invalid timers inline and prevents autosave until they are fixed", async () => {
    renderBuilder();
    const part = screen.getByRole("group", { name: "Speaking Part 2" });
    const input = within(part).getByRole("spinbutton", { name: "Response time (seconds)" });
    fireEvent.change(input, { target: { value: "0" } });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(within(part).getByRole("alert")).toHaveTextContent("Use a whole number from 1 to 3600 seconds.");
    expect(screen.getByRole("status")).toHaveTextContent("fix validation issues");
    expect(api.updateSpeakingPart).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Save now" }));
    await waitFor(() => expect(api.updateSpeakingPart).toHaveBeenCalledOnce());
  });

  it("selects the Speaking page and freezes an admin view under moderation", async () => {
    vi.mocked(api.getBuilderVersion).mockResolvedValue(version());
    vi.mocked(getVersionModeration).mockResolvedValue([{ id: crypto.randomUUID(), status: "PENDING" } as Awaited<ReturnType<typeof getVersionModeration>>[number]]);
    render(await BuilderEditorPage({ params: Promise.resolve({ testId, versionId }), searchParams: Promise.resolve({ workspace: "speaking" }) }));
    expect(screen.getByRole("link", { name: /SpeakingCreated/ })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "Create Speaking module" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Cue-card prompt" })).toBeDisabled();
  });

  it("summarizes authored Speaking parts rather than Writing tasks", () => {
    const units = builderContentSummary(version().modules[0]);
    expect(units).toHaveLength(3);
    expect(units[1].heading).toEqual({ message: "speaking.part", params: { number: 2 } });
    expect(units[1].excerpt).toContain("fictional tool");
  });

  it("supports read-only Speaking authoring in the existing moderation preview", () => {
    render(<ModerationPreview version={version()} requestId="fictional-request" />);
    expect(screen.getByRole("tab", { name: "Speaking" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("textbox", { name: "Cue-card prompt" })).toBeDisabled();
    expect(api.updateSpeakingPart).not.toHaveBeenCalled();
  });

  it("uses scoped short motion and disables it under reduced motion", () => {
    const css = postcss.parse(readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8"));
    let motion = ""; let reduced = "";
    css.walkRules(rule => {
      if (rule.selector.includes(".speaking-prompt-card")) {
        rule.walkDecls(decl => { motion += `${decl.prop}:${decl.value};`; });
      }
    });
    css.walkAtRules("media", rule => { if (rule.params === "(prefers-reduced-motion: reduce)") reduced += rule.toString(); });
    expect(motion).toContain("180ms");
    expect(reduced).toContain(".speaking-prompt-card");
    expect(reduced).toMatch(/animation:\s*none/);
    expect(reduced).toMatch(/transition:\s*none/);
  });

  it("lets an incomplete Part 2 move a recreated cue card before existing follow-ups", async () => {
    const value = version();
    const part = value.modules[0].speaking_parts![1];
    const main = part.prompts[0];
    part.prompts = [{ ...main, id: crypto.randomUUID(), order_index: 0, prompt_type: "FOLLOW_UP", preparation_seconds: 0, response_seconds: 60, config_json: { cue_points: [] } }, { ...main, order_index: 1 }];
    vi.mocked(api.reorderSpeakingPrompts).mockResolvedValue({ ...part, revision: 2, prompts: [...part.prompts].reverse().map((prompt, order_index) => ({ ...prompt, order_index })) });
    renderBuilder(value);
    const card = screen.getByRole("textbox", { name: "Cue-card prompt" }).closest("article")!;
    expect(within(card).getByRole("button", { name: "Move up" })).toBeEnabled();
    fireEvent.click(within(card).getByRole("button", { name: "Move up" }));
    await waitFor(() => expect(api.reorderSpeakingPrompts).toHaveBeenCalledWith(part.id, 1, [main.id, part.prompts[0].id]));
  });
});
