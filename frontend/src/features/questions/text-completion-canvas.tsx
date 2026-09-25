"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ComponentProps } from "react";
import { textCompletionIntegrityErrors } from "./text-completion-integrity";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type {
  QuestionGroupModel,
  QuestionModel,
  TextCompletionLayout,
  TextCompletionSegment,
} from "./types";

// React owns the span; the browser owns its text and selection while typing.
function EditableText({ text, ...props }: ComponentProps<"span"> & { text: string }) {
  const element = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (element.current && element.current.textContent !== text) element.current.textContent = text;
  }, [text]);
  return <span {...props} ref={element} />;
}

type Caret = { blockId: string; segmentId: string; offset: number };
type DropCaret = Caret & { x: number; y: number };
type DeleteTarget =
  | { kind: "gap"; questionId: string }
  | { kind: "paragraph"; blockId: string }
  | { kind: "sentence"; blockId: string }
  | null;

type LegacySentenceState = "none" | "safe" | "ambiguous";

function legacySentenceState(layout: TextCompletionLayout): LegacySentenceState {
  if (layout.mode !== "SENTENCE") return "none";
  let found = false;
  for (const block of layout.blocks) {
    const newlineSegments = block.segments.filter((segment) => segment.type === "TEXT" && /[\r\n]/.test(segment.text ?? ""));
    if (!newlineSegments.length) continue;
    found = true;
    if (block.segments.length !== 1 || newlineSegments.length !== 1) return "ambiguous";
  }
  return found ? "safe" : "none";
}

export function normalizeLegacySentenceLayout(layout: TextCompletionLayout): TextCompletionLayout {
  if (legacySentenceState(layout) !== "safe") return layout;
  return {
    ...layout,
    blocks: layout.blocks.flatMap((block) => {
      const segment = block.segments[0];
      if (segment.type !== "TEXT" || !/[\r\n]/.test(segment.text ?? "")) return [block];
      return (segment.text ?? "").split(/\r\n?|\n/).map((text, index) => ({
        id: index === 0 ? block.id : crypto.randomUUID(),
        segments: [{ id: index === 0 ? segment.id : crypto.randomUUID(), type: "TEXT" as const, text }],
      }));
    }),
  };
}

export function normalizeCompletionSegments(segments: TextCompletionSegment[]): TextCompletionSegment[] {
  const normalized: TextCompletionSegment[] = [];
  for (const source of segments) {
    const segment = { ...source };
    const previous = normalized.at(-1);
    if (segment.type === "TEXT" && previous?.type === "TEXT") {
      previous.text = `${previous.text ?? ""}${segment.text ?? ""}`;
      continue;
    }
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
    config: layout,
    // An invalid draft must remain intact so the author can repair it.
    questions: textCompletionIntegrityErrors({ ...group, config: layout }).length
      ? group.questions
      : questionIds.map((id, order_index) => ({ ...byId.get(id)!, number: firstNumber + order_index, order_index })),
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
  const pendingFocusSegmentId = useRef<string | null>(null);
  const legacyNormalizationChecked = useRef(false);
  const [selectedGapId, setSelectedGapId] = useState<string | null>(null);
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null);
  const [draggedGapId, setDraggedGapId] = useState<string | null>(null);
  const [dropCaret, setDropCaret] = useState<DropCaret | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const legacyState = legacySentenceState(layout);

  useEffect(() => {
    if (legacyNormalizationChecked.current) return;
    legacyNormalizationChecked.current = true;
    const normalized = normalizeLegacySentenceLayout(layout);
    if (normalized === layout) return;
    onChange(normalizeTextCompletionOrder({ ...group, config: normalized }, normalized, baseQuestionNumber));
  }, [baseQuestionNumber, group, layout, onChange]);

  useEffect(() => {
    const segmentId = pendingFocusSegmentId.current;
    if (!segmentId) return;
    const element = [...(canvas.current?.querySelectorAll<HTMLElement>("[data-completion-text-segment]") ?? [])]
      .find((item) => item.dataset.completionTextSegment === segmentId);
    if (!element) return;
    pendingFocusSegmentId.current = null;
    element.focus();
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    const blockId = element.closest<HTMLElement>("[data-completion-block]")?.dataset.completionBlock;
    if (blockId) activeCaret.current = { blockId, segmentId, offset: 0 };
  }, [layout.blocks]);

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
    if (!pendingFocusSegmentId.current) activeCaret.current = null;
    onChange(normalizeTextCompletionOrder(
      { ...group, questions },
      { ...nextLayout, blocks: nextLayout.blocks.map((block) => ({ ...block, segments: normalizeCompletionSegments(block.segments) })) },
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
    setActiveBlockId(blockId);
    setSelectedGapId(null);
  }

  function updateText(segmentId: string, text: string) {
    const blocks = layout.blocks.map((block) => ({
      ...block,
      segments: block.segments.map((segment) =>
        segment.id === segmentId ? { ...segment, text } : segment,
      ),
    }));
    // Typing changes text only: no merging, ID allocation, or order normalization.
    onChange({ ...group, config: { ...layout, blocks } });
  }

  function insertGap() {
    const focusedBlock = layout.blocks.find((block) => block.id === (activeCaret.current?.blockId ?? activeBlockId));
    const targetBlock = layout.mode === "SENTENCE" ? focusedBlock : focusedBlock ?? layout.blocks.at(-1);
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
      answer_key: { kind: "TEXT", accepted: [], case_sensitive: false },
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

  function removeBlock(blockId: string) {
    const block = layout.blocks.find((item) => item.id === blockId);
    if (!block) return;
    const removedIds = new Set(block.segments.flatMap((segment) =>
      segment.type === "GAP" && segment.question_id ? [segment.question_id] : [],
    ));
    commit(
      { ...layout, blocks: layout.blocks.filter((item) => item.id !== blockId) },
      group.questions.filter((question) => !question.id || !removedIds.has(question.id)),
    );
    if (activeBlockId === blockId) {
      activeCaret.current = null;
      setActiveBlockId(null);
    }
  }

  function moveBlock(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= layout.blocks.length) return;
    const blocks = [...layout.blocks];
    [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
    commit({ ...layout, blocks });
  }

  function addSentence() {
    const segmentId = crypto.randomUUID();
    const blockId = crypto.randomUUID();
    pendingFocusSegmentId.current = segmentId;
    activeCaret.current = { blockId, segmentId, offset: 0 };
    setActiveBlockId(blockId);
    commit({
      ...layout,
      blocks: [...layout.blocks, { id: blockId, segments: [{ id: segmentId, type: "TEXT", text: "" }] }],
    });
  }

  function splitSentence(blockId: string, segmentId: string, offset: number) {
    if (layout.mode !== "SENTENCE") return;
    const blockIndex = layout.blocks.findIndex((block) => block.id === blockId);
    if (blockIndex < 0) return;
    const block = layout.blocks[blockIndex];
    const segmentIndex = block.segments.findIndex((segment) => segment.id === segmentId && segment.type === "TEXT");
    if (segmentIndex < 0) return;
    const segment = block.segments[segmentIndex];
    const source = segment.text ?? "";
    const splitOffset = Math.max(0, Math.min(offset, source.length));
    const nextSegmentId = crypto.randomUUID();
    const nextBlockId = crypto.randomUUID();
    const firstBlock = {
      ...block,
      segments: normalizeCompletionSegments([
        ...block.segments.slice(0, segmentIndex),
        { ...segment, text: source.slice(0, splitOffset) },
      ]),
    };
    const nextBlock = {
      id: nextBlockId,
      segments: normalizeCompletionSegments([
        { id: nextSegmentId, type: "TEXT", text: source.slice(splitOffset) },
        ...block.segments.slice(segmentIndex + 1),
      ]),
    };
    const blocks = [...layout.blocks];
    blocks.splice(blockIndex, 1, firstBlock, nextBlock);
    pendingFocusSegmentId.current = nextSegmentId;
    activeCaret.current = { blockId: nextBlockId, segmentId: nextSegmentId, offset: 0 };
    setActiveBlockId(nextBlockId);
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
  const sentenceDeleteBlock = deleteTarget?.kind === "sentence"
    ? layout.blocks.find((block) => block.id === deleteTarget.blockId)
    : undefined;
  const sentenceDeleteHasGaps = sentenceDeleteBlock?.segments.some((segment) => segment.type === "GAP") ?? false;
  const recoveryBlock = layout.blocks.find((block) => block.id === activeBlockId) ?? layout.blocks.at(-1);
  const itemName = layout.mode === "SENTENCE" ? "Sentence" : "Paragraph";

  return <>
    <section className={`matching-section text-completion-authoring completion-authoring-${layout.mode.toLowerCase()}`}>
      <div className="matching-section-title">
        <div><h3>Completion text</h3><p>Edit the text inline. Gaps remain stable tokens linked to question UUIDs.</p></div>
        <label className="field-label">Mode<select className="select-field" value={layout.mode} onChange={(event) => commit({ ...layout, mode: event.target.value as TextCompletionLayout["mode"] })}><option value="SENTENCE">Sentence</option><option value="PASSAGE">Passage</option></select></label>
      </div>
      {legacyState === "ambiguous" ? <p role="alert" className="notice notice-warning mt-3">This sentence contains legacy line breaks mixed with gaps or multiple segments. It was left unchanged to protect linked questions. Split it into separate sentences manually.</p> : null}
      <div ref={canvas} className={`completion-canvas-list ${draggedGapId ? "is-dragging" : ""}`}>
        {layout.blocks.map((block, blockIndex) => <div key={block.id} data-completion-block={block.id} className={`completion-canvas-block ${layout.mode === "SENTENCE" ? "completion-sentence-item" : ""}`} onDragOver={(event) => {
          if (!draggedGapId) return;
          event.preventDefault();
          const next = resolvePointerCaret(event.clientX, event.clientY);
          setDropCaret(next?.blockId === block.id ? next : null);
        }} onDrop={(event) => { event.preventDefault(); dropGap(); setDraggedGapId(null); setDropCaret(null); }}>
          {layout.mode === "SENTENCE" ? <div className="completion-sentence-heading"><span>Sentence {blockIndex + 1}</span><div className="completion-sentence-actions">
            <button type="button" className="icon-button" disabled={blockIndex === 0} aria-label={`Move sentence ${blockIndex + 1} up`} onClick={() => moveBlock(blockIndex, -1)}>↑</button>
            <button type="button" className="icon-button" disabled={blockIndex === layout.blocks.length - 1} aria-label={`Move sentence ${blockIndex + 1} down`} onClick={() => moveBlock(blockIndex, 1)}>↓</button>
            {layout.blocks.length > 1 ? <button type="button" className="btn btn-danger-ghost" onClick={() => setDeleteTarget({ kind: "sentence", blockId: block.id })}>Remove sentence</button> : null}
          </div></div> : null}
          <div className="completion-inline-editor" aria-label={`${itemName} ${blockIndex + 1} completion editor`} onClick={(event) => {
            if (event.target !== event.currentTarget) return; // Native text caret and GAP buttons keep their behavior.
            setSelectedGapId(null);
            setActiveBlockId(block.id);
            const last = block.segments.at(-1);
            if (last?.type !== "TEXT") {
              const segmentId = crypto.randomUUID();
              pendingFocusSegmentId.current = segmentId;
              commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, segments: [...item.segments, { id: segmentId, type: "TEXT", text: "" }] } : item) });
              return;
            }
            const element = event.currentTarget.querySelector<HTMLElement>(`[data-completion-text-segment="${last.id}"]`);
            if (!element) return;
            element.focus();
            const range = document.createRange();
            range.selectNodeContents(element);
            range.collapse(false);
            const selection = window.getSelection();
            selection?.removeAllRanges();
            selection?.addRange(range);
            rememberCaret(block.id, last.id, element);
          }}>
            {block.segments.map((segment, segmentIndex) => segment.type === "TEXT" ? <EditableText
              text={segment.text ?? ""}
              key={segment.id}
              role="textbox"
              aria-label={`${itemName} ${blockIndex + 1} text segment ${segmentIndex + 1}`}
              aria-multiline={layout.mode === "PASSAGE"}
              contentEditable
              suppressContentEditableWarning
              data-completion-text-segment={segment.id}
              className="completion-editable-text"
              onFocus={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onKeyDown={(event) => {
                if (layout.mode !== "SENTENCE" || event.key !== "Enter") return;
                event.preventDefault();
                rememberCaret(block.id, segment.id, event.currentTarget);
                splitSentence(block.id, segment.id, activeCaret.current?.offset ?? 0);
              }}
              onKeyUp={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onMouseUp={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
              onInput={(event) => {
                rememberCaret(block.id, segment.id, event.currentTarget);
                const rawText = event.currentTarget.textContent ?? "";
                const text = layout.mode === "SENTENCE" ? rawText.replace(/[\r\n]+/g, " ") : rawText;
                if (text !== rawText) event.currentTarget.textContent = text;
                updateText(segment.id, text);
              }}
            /> : <button
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
      {group.questions.filter((question) => question.id && !layout.blocks.some((block) => block.segments.some((segment) => segment.type === "GAP" && segment.question_id === question.id))).map((question) => <button key={question.id} type="button" className="btn btn-secondary mt-3" onClick={() => {
        const block = recoveryBlock;
        if (!block) return;
        const gap = { id: crypto.randomUUID(), type: "GAP" as const, question_id: question.id };
        commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, segments: [...item.segments, gap] } : item) });
        setSelectedGapId(gap.id);
      }}>Add missing gap for Q{question.number} to {itemName.toLowerCase()} {layout.blocks.findIndex((block) => block.id === recoveryBlock?.id) + 1}</button>)}
      {selectedGap && textCompletionIntegrityErrors(group).length > 0 ? <label className="field-label mt-3">Link selected gap to question
        <select className="select-field" aria-label="Link selected gap to question" value={selectedQuestion?.id ?? ""} onChange={(event) => {
          if (!event.target.value) return;
          commit({ ...layout, blocks: layout.blocks.map((block) => ({ ...block, segments: block.segments.map((segment) => segment.id === selectedGap.id ? { ...segment, question_id: event.target.value } : segment) })) });
        }}>
          <option value="">Choose the intended question</option>
          {group.questions.filter((question) => question.id === selectedGap.question_id || !layout.blocks.some((block) => block.segments.some((segment) => segment.type === "GAP" && segment.question_id === question.id))).map((question) => <option key={question.id} value={question.id}>Q{question.number} — {String((question.answer_key.accepted as string[] | undefined)?.[0] ?? question.prompt)}</option>)}
        </select>
      </label> : null}
      {selectedGap && !selectedQuestion ? <div className="mt-3">
        <p className="text-sm">If the original answer is no longer available, create a new answer and configure it before saving.</p>
        <button type="button" className="btn btn-secondary" onClick={() => {
          const questionId = crypto.randomUUID();
          const question: QuestionModel = {
            id: questionId,
            number: (baseQuestionNumber ?? 1) + group.questions.length,
            prompt: "Answer",
            config: { max_words: 2, max_numbers: 1 },
            answer_key: { kind: "TEXT", accepted: [""], case_sensitive: false },
            order_index: group.questions.length,
          };
          commit({ ...layout, blocks: layout.blocks.map((block) => ({ ...block, segments: block.segments.map((segment) => segment.id === selectedGap.id ? { ...segment, question_id: questionId } : segment) })) }, [...group.questions, question]);
        }}>Create answer for this gap</button>
      </div> : null}
      {selectedGap && selectedQuestion ? <div className="completion-gap-actions" role="toolbar" aria-label={`Question ${selectedQuestion.number} gap actions`}>
        <strong>Q{selectedQuestion.number}</strong>
        <button type="button" className="btn btn-ghost" onClick={() => document.getElementById(`text-answer-${selectedQuestion.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>Edit answer</button>
        <button type="button" className="btn btn-secondary" aria-label={`Move Q${selectedQuestion.number} left`} onClick={() => moveGapByCharacter(selectedGap.id, -1)}>Move left</button>
        <button type="button" className="btn btn-secondary" aria-label={`Move Q${selectedQuestion.number} right`} onClick={() => moveGapByCharacter(selectedGap.id, 1)}>Move right</button>
        <button type="button" className="btn btn-danger-ghost" onClick={() => setDeleteTarget({ kind: "gap", questionId: selectedQuestion.id! })}>Remove gap</button>
      </div> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary" disabled={layout.mode === "SENTENCE" && !activeBlockId} onClick={insertGap}>+ Insert gap</button>
        {layout.mode === "SENTENCE" ? <button type="button" className="btn btn-secondary" onClick={addSentence}>+ Add sentence</button> : null}
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
      onConfirm={() => { if (deleteTarget?.kind === "paragraph") removeBlock(deleteTarget.blockId); setDeleteTarget(null); }}
    />
    <ConfirmDialog
      open={deleteTarget?.kind === "sentence"}
      title="Remove this sentence?"
      description={sentenceDeleteHasGaps ? "Removing this sentence will also remove its linked questions and answer configuration." : "This sentence will be removed."}
      confirmLabel="Remove sentence"
      pending={false}
      onCancel={() => setDeleteTarget(null)}
      onConfirm={() => { if (deleteTarget?.kind === "sentence") removeBlock(deleteTarget.blockId); setDeleteTarget(null); }}
    />
  </>;
}
