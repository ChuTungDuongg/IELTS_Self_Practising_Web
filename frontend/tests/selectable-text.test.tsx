import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SelectableText } from "@/features/highlighting/selectable-text";

function selectText(node: Node, start: number, end: number) {
  const range = document.createRange();
  range.setStart(node, start);
  range.setEnd(node, end);
  Object.defineProperty(range, "getBoundingClientRect", { value: () => ({ left: 10, top: 20, width: 40, height: 10 }) });
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
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
    render(<SelectableText text="Tourism supports jobs" target={{ target_kind: "QUESTION_PROMPT", target_id: targetId }} controller={{ readOnly: true, highlights: [{ id: crypto.randomUUID(), target_kind: "QUESTION_PROMPT", target_id: targetId, segment_id: null, passage_id: null, start_block_id: null, end_block_id: null, start_offset: 0, end_offset: 7, selected_text: "Tourism", created_at: new Date().toISOString() }] }} />);
    expect(screen.getByText("Tourism").tagName).toBe("MARK");
  });
});
