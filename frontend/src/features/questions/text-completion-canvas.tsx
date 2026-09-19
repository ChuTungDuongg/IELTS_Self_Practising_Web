"use client";

import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type {
  QuestionGroupModel,
  QuestionModel,
  TextCompletionLayout,
  TextCompletionSegment,
} from "./types";

type Caret = { blockId: string; segmentId: string; offset: number };
type DropCaret = Caret & { x: number; y: number };
type DeleteTarget =
  | { kind: "gap"; questionId: string }
  | { kind: "paragraph"; blockId: string }
  | null;

export function normalizeCompletionSegments(segments: TextCompletionSegment[]): TextCompletionSegment[] {
  const normalized: TextCompletionSegment[] = [];
  for (const source of segments) {
    const segment = { ...source };
    const previous = normalized.at(-1);
    if (segment.type === "TEXT" && previous?.type === "TEXT") {
      previous.text = `${previous.text ?? ""}${segment.text ?? ""}`;
      continue;
    }
    if (segment.type === "TEXT" && !segment.text && segments.length > 1) continue;
    normalized.push(segment);
  }
  return normalized.length
    ? normalized
    : [{ id: crypto.randomUUID(), type: "TEXT", text: "" }];
}

export function normalizeTextCompletionOrder(
  group: QuestionGroupModel,
  layout: TextCompletionLayout,
  baseQuestionNumber?: number,
): QuestionGroupModel {
  const questionIds = layout.blocks.flatMap((block) =>
    block.segments.flatMap((segment) =>
      segment.type === "GAP" && segment.question_id ? [segment.question_id] : [],
    ),
  );
  const byId = new Map(group.questions.flatMap((question) => question.id ? [[question.id, question]] : []));
  const firstNumber = baseQuestionNumber
    ?? (group.questions.length ? Math.min(...group.questions.map((question) => question.number)) : 1);
  return {
    ...group,
    config: { ...layout, blocks: layout.blocks.map((block) => ({ ...block, segments: normalizeCompletionSegments(block.segments) })) },
    questions: questionIds.flatMap((id, order_index) => {
      const question = byId.get(id);
      return question ? [{ ...question, number: firstNumber + order_index, order_index }] : [];
    }),
  };
}

export function TextCompletionCanvas({
  group,
  onChange,
  baseQuestionNumber,
}: {
  group: QuestionGroupModel;
  onChange: (group: QuestionGroupModel) => void;
  baseQuestionNumber?: number;
}) {
  const layout = group.config as unknown as TextCompletionLayout;
  const canvas = useRef<HTMLDivElement>(null);
  const activeCaret = useRef<Caret | null>(null);
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null);
  const [draggedGapId, setDraggedGapId] = useState<string | null>(null);
  const [dropCaret, setDropCaret] = useState<DropCaret | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  useEffect(() => {
    if (!draggedGapId) return;
    const cancel = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDraggedGapId(null);
        setDropCaret(null);
      }
    };
    document.addEventListener("keydown", cancel);
    return () => document.removeEventListener("keydown", cancel);
  }, [draggedGapId]);

  function commit(nextLayout: TextCompletionLayout, questions = group.questions) {
    onChange(normalizeTextCompletionOrder(
      { ...group, questions },
      nextLayout,
      baseQuestionNumber,
    ));
  }

  function rememberCaret(blockId: string, segmentId: string, element: HTMLElement) {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !element.contains(selection.anchorNode)) return;
    const range = selection.getRangeAt(0).cloneRange();
    range.selectNodeContents(element);
    range.setEnd(selection.anchorNode!, selection.anchorOffset);
    activeCaret.current = {
      blockId,
      segmentId,
      offset: Math.min(element.textContent?.length ?? 0, range.toString().length),
    };
  }

  function updateText(segmentId: string, text: string) {
    const blocks = layout.blocks.map((block) => ({
      ...block,
      segments: block.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, text } : segment,
      ),
    }));
    commit({ ...layout, blocks });
  }

  function insertGap() {
    const targetBlock = layout.blocks.find((block) => block.id === activeCaret.current?.blockId)
      ?? layout.blocks.at(-1);
    if (!targetBlock) return;
    const target = targetBlock.segments.find((segment) =>
      segment.id === activeCaret.current?.segmentId && segment.type === "TEXT",
    ) ?? [...targetBlock.segments].reverse().find((segment) => segment.type === "TEXT");
    const questionId = crypto.randomUUID();
    const question: QuestionModel = {
      id: questionId,
      number: (baseQuestionNumber ?? 1) + group.questions.length,
      prompt: "Answer",
      config: { max_words: 2, max_numbers: 1 },
      answer_key: { kind: "TEXT", accepted: ["answer"], case_sensitive: false },
      order_index: group.questions.length,
    };
    const gap: TextCompletionSegment = {
      id: crypto.randomUUID(),
      type: "GAP",
      question_id: questionId,
    };
    const blocks = layout.blocks.map((block) => {
      if (block.id !== targetBlock.id) return block;
      if (!target) return { ...block, segments: [...block.segments, gap] };
      const source = target.text ?? "";
      const requestedOffset = activeCaret.current?.segmentId === target.id
        ? activeCaret.current.offset
        : source.length;
      const offset = Math.max(0, Math.min(requestedOffset, source.length));
      return {
        ...block,
        segments: block.segments.flatMap((segment) => segment.id === target.id ? [
          { ...segment, text: source.slice(0, offset) },
          gap,
          { id: crypto.randomUUID(), type: "TEXT" as const, text: source.slice(offset) },
        ] : [segment]),
      };
    });
    activeCaret.current = null;
    setSelectedGapId(gap.id);
    commit({ ...layout, blocks }, [...group.questions, question]);
  }

  function removeGap(questionId: string) {
    const blocks = layout.blocks.map((block) => ({
      ...block,
      segments: normalizeCompletionSegments(block.segments.filter((segment) =>
        !(segment.type === "GAP" && segment.question_id === questionId),
      )),
    }));
    setSelectedGapId(null);
    commit(
      { ...layout, blocks },
      group.questions.filter((question) => question.id !== questionId),
    );
  }

  function removeParagraph(blockId: string) {
    const block = layout.blocks.find((item) => item.id === blockId);
    if (!block) return;
    const removedIds = new Set(block.segments.flatMap((segment) =>
      segment.type === "GAP" && segment.question_id ? [segment.question_id] : [],
    ));
    commit(
      { ...layout, blocks: layout.blocks.filter((item) => item.id !== blockId) },
      group.questions.filter((question) => !question.id || !removedIds.has(question.id)),
    );
  }

  function moveBlock(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= layout.blocks.length) return;
    const blocks = [...layout.blocks];
    [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
    commit({ ...layout, blocks });
  }

  function moveGapByCharacter(gapId: string, direction: -1 | 1) {
    const blocks = layout.blocks.map((block) => {
      const gapIndex = block.segments.findIndex((segment) => segment.id === gapId);
      if (gapIndex < 0) return block;
      const segments = block.segments.map((segment) => ({ ...segment }));
      if (direction < 0) {
        const before = segments[gapIndex - 1];
        if (before?.type !== "TEXT" || !(before.text ?? "").length) return block;
        const moved = before.text!.slice(-1);
        before.text = before.text!.slice(0, -1);
        const after = segments[gapIndex + 1];
        if (after?.type === "TEXT") after.text = moved + (after.text ?? "");
        else segments.splice(gapIndex + 1, 0, { id: crypto.randomUUID(), type: "TEXT", text: moved });
      } else {
        const after = segments[gapIndex + 1];
        if (after?.type !== "TEXT" || !(after.text ?? "").length) return block;
        const moved = after.text![0];
        after.text = after.text!.slice(1);
        const before = segments[gapIndex - 1];
        if (before?.type === "TEXT") before.text = (before.text ?? "") + moved;
        else segments.splice(gapIndex, 0, { id: crypto.randomUUID(), type: "TEXT", text: moved });
      }
      return { ...block, segments };
    });
    commit({ ...layout, blocks });
  }

  function resolvePointerCaret(clientX: number, clientY: number): DropCaret | null {
    const caretDocument = document as Document & {
      caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
      caretRangeFromPoint?: (x: number, y: number) => Range | null;
    };
    const position = caretDocument.caretPositionFromPoint?.(clientX, clientY);
    const fallback = position ? null : caretDocument.caretRangeFromPoint?.(clientX, clientY);
    const node = position?.offsetNode ?? fallback?.startContainer;
    const rawOffset = position?.offset ?? fallback?.startOffset;
    const parent = node instanceof Element ? node : node?.parentElement;
    const segment = parent?.closest<HTMLElement>("[data-completion-text-segment]");
    const block = segment?.closest<HTMLElement>("[data-completion-block]");
    if (!node || rawOffset === undefined || !segment || !block) return null;
    const textLength = segment.textContent?.length ?? 0;
    let canonicalOffset = rawOffset;
    if (segment.contains(node)) {
      try {
        const range = document.createRange();
        range.selectNodeContents(segment);
        range.setEnd(node, rawOffset);
        canonicalOffset = range.toString().length;
      } catch {
        canonicalOffset = rawOffset;
      }
    }
    return {
      blockId: block.dataset.completionBlock!,
      segmentId: segment.dataset.completionTextSegment!,
      offset: Math.max(0, Math.min(canonicalOffset, textLength)),
      x: clientX,
      y: clientY,
    };
  }

  function dropGap() {
    if (!draggedGapId || !dropCaret) return;
    const sourceBlock = layout.blocks.find((block) =>
      block.segments.some((segment) => segment.id === draggedGapId),
    );
    if (!sourceBlock || sourceBlock.id !== dropCaret.blockId) return;
    const gap = sourceBlock.segments.find((segment) => segment.id === draggedGapId);
    if (!gap) return;
    const blocks = layout.blocks.map((block) => {
      if (block.id !== sourceBlock.id) return block;
      const withoutGap = block.segments.filter((segment) => segment.id !== draggedGapId);
      const segments = withoutGap.flatMap((segment) => {
        if (segment.id !== dropCaret.segmentId || segment.type !== "TEXT") return [segment];
        const source = segment.text ?? "";
        const offset = Math.max(0, Math.min(dropCaret.offset, source.length));
        return [
          { ...segment, text: source.slice(0, offset) },
          gap,
          { id: crypto.randomUUID(), type: "TEXT" as const, text: source.slice(offset) },
        ];
      });
      return { ...block, segments };
    });
    commit({ ...layout, blocks });
  }

  const selectedGap = layout.blocks.flatMap((block) => block.segments)
    .find((segment) => segment.id === selectedGapId && segment.type === "GAP");
  const selectedQuestion = selectedGap?.question_id
    ? group.questions.find((question) => question.id === selectedGap.question_id)
    : undefined;

  return <>
    <section className="matching-section text-completion-authoring">
      <div className="matching-section-title">
        <div><h3>Completion text</h3><p>Edit the text inline. Gaps remain stable tokens linked to question UUIDs.</p></div>
        <label className="field-label">Mode<select className="select-field" value={layout.mode} onChange={(event) => commit({ ...layout, mode: event.target.value as TextCompletionLayout["mode"] })}><option value="SENTENCE">Sentence</option><option value="PASSAGE">Passage</option></select></label>
      </div>
      <div ref={canvas} className={`completion-canvas-list ${draggedGapId ? "is-dragging" : ""}`}>
        {layout.blocks.map((block, blockIndex) => <div key={block.id} data-completion-block={block.id} className="completion-canvas-block" onDragOver={(event) => {
          if (!draggedGapId) return;
          event.preventDefault();
          const next = resolvePointerCaret(event.clientX, event.clientY);
          setDropCaret(next?.blockId === block.id ? next : null);
        }} onDrop={(event) => { event.preventDefault(); dropGap(); setDraggedGapId(null); setDropCaret(null); }}>
          <div className="completion-inline-editor" aria-label={`Paragraph ${blockIndex + 1} completion editor`}>
            {block.segments.map((segment, segmentIndex) => segment.type === "TEXT" ? <span
              key={segment.id}
              role="textbox"
              aria-label={`Paragraph ${blockIndex + 1} text segment ${segmentIndex + 1}`}
              aria-multiline="true"
              contentEditable
              suppressContentEditableWarning
              data-completion-text-segment={segment.id}
              className="completion-editable-text"
              onFocus={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onKeyUp={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onMouseUp={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onInput={(event) => {
                rememberCaret(block.id, segment.id, event.currentTarget);
                updateText(segment.id, event.currentTarget.textContent ?? "");
              }}
            >{segment.text ?? ""}</span> : <button
              key={segment.id}
              type="button"
              draggable
              className={`completion-gap-token ${selectedGapId === segment.id ? "is-selected" : ""} ${draggedGapId === segment.id ? "is-dragged" : ""}`}
              aria-label={`Gap question ${group.questions.find((question) => question.id === segment.question_id)?.number ?? "unknown"}`}
              aria-pressed={selectedGapId === segment.id}
              onClick={() => setSelectedGapId(segment.id)}
              onDragStart={(event) => {
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", segment.id);
                setDraggedGapId(segment.id);
                setSelectedGapId(segment.id);
              }}
              onDragEnd={() => { setDraggedGapId(null); setDropCaret(null); }}
            >Q{group.questions.find((question) => question.id === segment.question_id)?.number ?? "?"}</button>)}
          </div>
          {layout.mode === "PASSAGE" ? <div className="completion-paragraph-actions">
            <button type="button" className="icon-button" disabled={blockIndex === 0} aria-label={`Move paragraph ${blockIndex + 1} up`} onClick={() => moveBlock(blockIndex, -1)}>↑</button>
            <button type="button" className="icon-button" disabled={blockIndex === layout.blocks.length - 1} aria-label={`Move paragraph ${blockIndex + 1} down`} onClick={() => moveBlock(blockIndex, 1)}>↓</button>
            {layout.blocks.length > 1 ? <button type="button" className="btn btn-danger-ghost" onClick={() => setDeleteTarget({ kind: "paragraph", blockId: block.id })}>Remove paragraph</button> : null}
          </div> : null}
        </div>)}
      </div>
      {dropCaret ? <span className="completion-drop-indicator" style={{ left: dropCaret.x, top: dropCaret.y }} aria-label="Gap drop position" /> : null}
      {selectedGap && selectedQuestion ? <div className="completion-gap-actions" role="toolbar" aria-label={`Question ${selectedQuestion.number} gap actions`}>
        <strong>Q{selectedQuestion.number}</strong>
        <button type="button" className="btn btn-ghost" onClick={() => document.getElementById(`text-answer-${selectedQuestion.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>Edit answer</button>
        <button type="button" className="btn btn-secondary" aria-label={`Move Q${selectedQuestion.number} left`} onClick={() => moveGapByCharacter(selectedGap.id, -1)}>Move left</button>
        <button type="button" className="btn btn-secondary" aria-label={`Move Q${selectedQuestion.number} right`} onClick={() => moveGapByCharacter(selectedGap.id, 1)}>Move right</button>
        <button type="button" className="btn btn-danger-ghost" onClick={() => setDeleteTarget({ kind: "gap", questionId: selectedQuestion.id! })}>Remove gap</button>
      </div> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary" onClick={insertGap}>+ Insert gap</button>
        {layout.mode === "PASSAGE" ? <button type="button" className="btn btn-secondary" onClick={() => commit({ ...layout, blocks: [...layout.blocks, { id: crypto.randomUUID(), segments: [{ id: crypto.randomUUID(), type: "TEXT", text: "New paragraph" }] }] })}>+ Add paragraph</button> : null}
      </div>
    </section>
    <ConfirmDialog
      open={deleteTarget?.kind === "gap"}
      title="Remove this gap?"
      description="The linked question and its answer configuration will also be removed."
      confirmLabel="Remove gap"
      pending={false}
      onCancel={() => setDeleteTarget(null)}
      onConfirm={() => { if (deleteTarget?.kind === "gap") removeGap(deleteTarget.questionId); setDeleteTarget(null); }}
    />
    <ConfirmDialog
      open={deleteTarget?.kind === "paragraph"}
      title="Remove this paragraph?"
      description="Every gap and linked question in this paragraph will also be removed."
      confirmLabel="Remove paragraph"
      pending={false}
      onCancel={() => setDeleteTarget(null)}
      onConfirm={() => { if (deleteTarget?.kind === "paragraph") removeParagraph(deleteTarget.blockId); setDeleteTarget(null); }}
    />
  </>;
}
