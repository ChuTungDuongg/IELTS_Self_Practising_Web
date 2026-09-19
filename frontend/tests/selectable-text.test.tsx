import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
