import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { MatchingHeadingsRenderer, TrueFalseNotGivenRenderer } from "@/features/questions/renderers";
import { questionRegistry } from "@/features/questions/registry";
import type { ExamGroup } from "@/features/questions/types";
import { SelectableText } from "@/features/highlighting/selectable-text";
import type { Highlight } from "@/lib/api/exam";

function selectText(node: Node, start: number, end: number) {
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, end);
  Object.defineProperty(range, "getBoundingClientRect", { value: () => ({ left: 10, top: 20, width: 40, height: 10 }) });
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
}

function storedHighlight(targetId: string): Highlight {
  return { id: crypto.randomUUID(), target_kind: "QUESTION_PROMPT", target_id: targetId, segment_id: null, passage_id: null, start_block_id: null, end_block_id: null, start_offset: 0, end_offset: 7, selected_text: "Tourism", created_at: new Date().toISOString() };
}

describe("selectable text", () => {
  it("does not persist on selection and creates exactly once after confirmation", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: crypto.randomUUID() }} controller={{ highlights: [], onCreate }} />);
    const text = screen.getByText("Tourism supports jobs");
    selectText(text.firstChild!, 0, 7);
    fireEvent.mouseUp(text);
    expect(onCreate).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Highlight" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate.mock.calls[0][0]).toMatchObject({ start_offset: 0, end_offset: 7, selected_text: "Tourism" });
  });

  it("cancels a pending selection on Escape", () => {
    const onCreate = vi.fn();
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: crypto.randomUUID() }} controller={{ highlights: [], onCreate }} />);
    const text = screen.getByText("Tourism supports jobs");
    selectText(text.firstChild!, 0, 7);
    fireEvent.mouseUp(text);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Highlight" })).not.toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("cancels on an outside click without creating a highlight", () => {
    const onCreate = vi.fn();
    render(<div><SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: crypto.randomUUID() }} controller={{ highlights: [], onCreate }} /><button type="button">Outside</button></div>);
    const text = screen.getByText("Tourism supports jobs");
    selectText(text.firstChild!, 0, 7);
    fireEvent.mouseUp(text);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("button", { name: "Highlight" })).not.toBeInTheDocument();
    expect(onCreate).not.toHaveBeenCalled();
  });

  it("renders stored highlights read-only in review", () => {
    const targetId = crypto.randomUUID();
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: targetId }} controller={{ readOnly: true, highlights: [storedHighlight(targetId)] }} />);
    expect(screen.getByText("Tourism").tagName).toBe("MARK");
    expect(screen.queryByRole("button", { name: /Highlight: Tourism/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove highlight" })).not.toBeInTheDocument();
  });

  it("opens options before deleting an existing highlight and never uses window.confirm", async () => {
    const targetId = crypto.randomUUID();
    const item = storedHighlight(targetId);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm");
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: targetId }} controller={{ highlights: [item], onDelete }} />);

    window.getSelection()?.removeAllRanges();
    fireEvent.click(screen.getByRole("button", { name: "Highlight: Tourism. Open options" }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Highlight options" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove highlight" }));

    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(item.id));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(confirm).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("keeps a highlight and its options visible when deletion fails", async () => {
    const targetId = crypto.randomUUID();
    const item = storedHighlight(targetId);
    const onDelete = vi.fn().mockRejectedValue(new Error("offline"));
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: targetId }} controller={{ highlights: [item], onDelete }} />);

    window.getSelection()?.removeAllRanges();
    fireEvent.keyDown(screen.getByRole("button", { name: "Highlight: Tourism. Open options" }), { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "Remove highlight" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not remove");
    expect(screen.getByRole("button", { name: "Highlight: Tourism. Open options" }).tagName).toBe("MARK");
    expect(screen.getByRole("dialog", { name: "Highlight options" })).toBeInTheDocument();
  });

  it("dismisses highlight options with Escape or an outside click", () => {
    const targetId = crypto.randomUUID();
    render(<div><SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: targetId }} controller={{ highlights: [storedHighlight(targetId)], onDelete: vi.fn() }} /><button type="button">Outside options</button></div>);
    const mark = screen.getByRole("button", { name: "Highlight: Tourism. Open options" });

    window.getSelection()?.removeAllRanges();
    fireEvent.click(mark);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Highlight options" })).not.toBeInTheDocument();

    fireEvent.click(mark);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Outside options" }));
    expect(screen.queryByRole("dialog", { name: "Highlight options" })).not.toBeInTheDocument();
  });
});

describe("Matching Headings option highlighting", () => {
  it("creates, restores, and removes a highlight using the group and stable option IDs", async () => {
    const groupId = crypto.randomUUID();
    const optionId = crypto.randomUUID();
    const questionId = crypto.randomUUID();
    const blockId = crypto.randomUUID();
    const group = {
      id: groupId,
      question_type: "matching_headings",
      instruction: "Choose the correct heading.",
      order_index: 0,
      config: { options: [
        { id: optionId, label: "i", text: "Earning foreign exchange through tourism" },
        { id: crypto.randomUUID(), label: "ii", text: "The development of mass tourism" },
      ] },
      questions: [{ id: questionId, number: 1, prompt: "Paragraph A", config: { target_block_id: blockId }, order_index: 0 }],
    } as ExamGroup;
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const view = render(
      <MatchingHeadingsRenderer
        group={group}
        values={{}}
        passageBlocks={[{ id: blockId, type: "paragraph", label: "A", text: "Fictional paragraph" }]}
        highlighting={{ highlights: [], onCreate, onDelete }}
      />,
    );
    const optionText = screen.getByText("Earning foreign exchange through tourism");
    expect(optionText.closest("li")).toHaveClass("matching-heading-option");
    selectText(optionText.firstChild!, 0, 7);
    fireEvent.mouseUp(optionText);
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({
      target_kind: "QUESTION_GROUP_OPTION",
      target_id: groupId,
      segment_id: optionId,
      start_offset: 0,
      end_offset: 7,
      selected_text: "Earning",
    })));

    const stored: Highlight = {
      id: crypto.randomUUID(),
      target_kind: "QUESTION_GROUP_OPTION",
      target_id: groupId,
      segment_id: optionId,
      passage_id: null,
      start_block_id: null,
      end_block_id: null,
      start_offset: 0,
      end_offset: 7,
      selected_text: "Earning",
      created_at: new Date().toISOString(),
    };
    view.rerender(
      <MatchingHeadingsRenderer
        group={group}
        values={{}}
        passageBlocks={[{ id: blockId, type: "paragraph", label: "A", text: "Fictional paragraph" }]}
        highlighting={{ highlights: [stored], onCreate, onDelete }}
      />,
    );
    window.getSelection()?.removeAllRanges();
    fireEvent.click(screen.getByRole("button", { name: "Highlight: Earning. Open options" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove highlight" }));
    await waitFor(() => expect(onDelete).toHaveBeenCalledWith(stored.id));
    expect(screen.getByRole("combobox", { name: "Question 1" })).toBeInTheDocument();
  });
});


describe("inline-safe highlight portals", () => {
  it("keeps both dialogs outside a real QuestionHeader paragraph without nesting warnings", async () => {
    const error = vi.spyOn(console, "error");
    const group = { ...questionRegistry.true_false_not_given.createDefault(5), id: crypto.randomUUID() } as ExamGroup;
    group.questions[0].prompt = "Tourism supports jobs";
    const onCreate = vi.fn().mockRejectedValue(new Error("offline"));
    const onDelete = vi.fn().mockResolvedValue(undefined);
    const view = render(<TrueFalseNotGivenRenderer group={group} values={{}} highlighting={{ highlights: [], onCreate, onDelete }} />);
    const text = screen.getByText("Tourism supports jobs");
    selectText(text.firstChild!, 0, 7);
    fireEvent.mouseUp(text);
    const create = screen.getByRole("dialog", { name: "Create highlight" });
    expect(create.parentElement).toBe(document.body);
    expect(create).toHaveStyle({ left: "30px", top: "12px" });
    expect(view.container.querySelector("p div, p p, span div")).toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Highlight" }));
    fireEvent.click(screen.getByRole("button", { name: "Highlight" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not create");
    expect(onCreate).toHaveBeenCalledOnce();
    fireEvent.keyDown(document, { key: "Escape" });
    window.getSelection()!.removeAllRanges();
    view.rerender(<TrueFalseNotGivenRenderer group={group} values={{}} highlighting={{ highlights: [storedHighlight(group.questions[0].id)], onCreate, onDelete }} />);
    fireEvent.click(screen.getByRole("button", { name: /Highlight: Tourism/ }));
    expect(screen.getByRole("dialog", { name: "Highlight options" }).parentElement).toBe(document.body);
    expect(view.container.querySelector("p div, p p, span div")).toBeNull();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Remove highlight" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove highlight" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onDelete).toHaveBeenCalledOnce();
    expect(error.mock.calls.flat().join(" ")).not.toMatch(/descendant|nested|hydration/i);
    error.mockRestore();
  });

  it("renders inline server markup with no portal on the initial render", () => {
    const html = renderToString(<p><SelectableText text="Fictional text" target={{ target_kind: "QUESTION_PROMPT", target_id: "test" }} controller={{ highlights: [], onCreate: vi.fn() }} /></p>);
    expect(html).not.toContain("<div");
    expect(html).not.toContain("dialog");
    expect(html).toContain("Fictional text");
  });

  it("closes peers and dismisses stale viewport positions on scroll", () => {
    render(<><SelectableText text="First fictional text" target={{ target_kind: "QUESTION_PROMPT", target_id: "first" }} controller={{ highlights: [], onCreate: vi.fn() }} /><SelectableText text="Second fictional text" target={{ target_kind: "QUESTION_PROMPT", target_id: "second" }} controller={{ highlights: [], onCreate: vi.fn() }} /></>);
    const first = screen.getByText("First fictional text");
    selectText(first.firstChild!, 0, 5);
    fireEvent.mouseUp(first);
    const second = screen.getByText("Second fictional text");
    selectText(second.firstChild!, 0, 6);
    fireEvent.mouseUp(second);
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog")).toHaveTextContent("Second");
    fireEvent.scroll(document);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
