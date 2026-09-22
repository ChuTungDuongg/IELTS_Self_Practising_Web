"use client";

import { useLayoutEffect, useRef, useState, type ComponentProps, type MouseEvent as ReactMouseEvent } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { EditorProps } from "./editors";
import { normalizeNoteCompletionOrder } from "./note-completion";
import type {
  NoteBlockStyle,
  NoteCompletionBlock,
  NoteCompletionLayout,
  NoteCompletionSegment,
  QuestionModel,
} from "./types";

function EditableText({ text, ...props }: ComponentProps<"span"> & { text: string }) {
  const element = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    if (element.current && element.current.textContent !== text) element.current.textContent = text;
  }, [text]);
  return <span {...props} ref={element} />;
}

type Caret = { blockId: string; segmentId: string; offset: number };
type PendingFocus = { segmentId: string; offset: number; preserveGapSelection?: boolean };
type DropCaret = Caret & { x: number; y: number };
type DeleteTarget =
  | { kind: "gap"; segmentId: string; questionId: string }
  | { kind: "block"; blockId: string; questionNumbers: number[] }
  | null;

function compactSegments(segments: NoteCompletionSegment[]): NoteCompletionSegment[] {
  const compacted: NoteCompletionSegment[] = [];
  for (const source of segments) {
    const segment = { ...source };
    const previous = compacted.at(-1);
    if (segment.type === "TEXT" && previous?.type === "TEXT") {
      previous.text += segment.text;
    } else {
      compacted.push(segment);
    }
  }
  return compacted.length ? compacted : [{ id: crypto.randomUUID(), type: "TEXT", text: "" }];
}

function nextBlockStyle(style: NoteBlockStyle): NoteBlockStyle {
  if (style === "BULLET" || style === "HEADING") return "BULLET";
  return "TEXT";
}

function questionList(numbers: number[]): string {
  const labels = numbers.map((number) => `Q${number}`);
  if (labels.length < 2) return labels[0] ?? "the linked question";
  return `${labels.slice(0, -1).join(", ")} and ${labels.at(-1)}`;
}

export function NoteCompletionEditor({ group, onChange, baseQuestionNumber }: EditorProps) {
  const layout = group.config.layout as NoteCompletionLayout;
  const canvas = useRef<HTMLDivElement>(null);
  const activeCaret = useRef<Caret | null>(null);
  const pendingFocus = useRef<PendingFocus | null>(null);
  const shortcutKeyUpSource = useRef<string | null>(null);
  const initialGap = layout.blocks.flatMap((block) => block.segments).find((segment) => segment.type === "GAP");
  const [selectedGapId, setSelectedGapId] = useState(initialGap?.id ?? "");
  const [activeBlockId, setActiveBlockId] = useState(layout.blocks[0]?.id ?? "");
  const [draggedGapId, setDraggedGapId] = useState("");
  const [dropCaret, setDropCaret] = useState<DropCaret | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);

  useLayoutEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    const element = [...(canvas.current?.querySelectorAll<HTMLElement>("[data-note-text-segment]") ?? [])]
      .find((item) => item.dataset.noteTextSegment === target.segmentId);
    if (!element) return;
    element.focus();
    pendingFocus.current = null;
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    const node = element.firstChild;
    if (node?.nodeType === Node.TEXT_NODE) {
      range.setStart(node, Math.min(target.offset, node.textContent?.length ?? 0));
      range.collapse(true);
    }
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    const blockId = element.closest<HTMLElement>("[data-note-block]")?.dataset.noteBlock;
    if (blockId) activeCaret.current = { blockId, segmentId: target.segmentId, offset: target.offset };
  }, [layout.blocks]);

  function commit(nextLayout: NoteCompletionLayout, questions = group.questions) {
    onChange(normalizeNoteCompletionOrder(
      { ...group, questions },
      {
        ...nextLayout,
        blocks: nextLayout.blocks.map((block) => ({ ...block, segments: compactSegments(block.segments) })),
      },
      baseQuestionNumber,
    ));
  }

  function rememberCaret(blockId: string, segmentId: string, element: HTMLElement, clearGapSelection = true) {
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
    if (clearGapSelection) setSelectedGapId("");
  }

  function focusTextSegment(blockId: string, segmentId: string, offset: number) {
    const element = [...(canvas.current?.querySelectorAll<HTMLElement>("[data-note-text-segment]") ?? [])]
      .find((item) => item.dataset.noteTextSegment === segmentId);
    if (!element) return;
    element.focus();
    const range = document.createRange();
    range.selectNodeContents(element);
    range.collapse(false);
    const node = element.firstChild;
    if (node?.nodeType === Node.TEXT_NODE) {
      range.setStart(node, Math.min(offset, node.textContent?.length ?? 0));
      range.collapse(true);
    }
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    activeCaret.current = { blockId, segmentId, offset };
    setActiveBlockId(blockId);
    setSelectedGapId("");
  }

  function focusBlockContent(event: ReactMouseEvent<HTMLDivElement>, block: NoteCompletionBlock) {
    const target = event.target as Element;
    if (target.closest("[data-note-text-segment], .completion-gap-token")) return;

    setActiveBlockId(block.id);
    setSelectedGapId("");
    const last = block.segments.at(-1);
    if (last?.type !== "TEXT") {
      const segmentId = crypto.randomUUID();
      pendingFocus.current = { segmentId, offset: 0 };
      commit({
        ...layout,
        blocks: layout.blocks.map((item) => item.id === block.id ? {
          ...item,
          segments: [...item.segments, { id: segmentId, type: "TEXT", text: "" }],
        } : item),
      });
      return;
    }

    focusTextSegment(block.id, last.id, last.text.length);
  }

  function createQuestion(offset: number): QuestionModel {
    return {
      id: crypto.randomUUID(),
      number: (baseQuestionNumber ?? 1) + group.questions.length + offset,
      prompt: "Note gap",
      config: { max_words: 2, max_numbers: 1 },
      answer_key: { kind: "TEXT", accepted: ["answer"], case_sensitive: false },
      order_index: group.questions.length + offset,
    };
  }

  function updateText(blockId: string, segmentId: string, text: string) {
    const parts = text.split("{{gap}}");
    if (parts.length === 1) {
      commit({
        ...layout,
        blocks: layout.blocks.map((block) => block.id !== blockId ? block : {
          ...block,
          segments: block.segments.map((segment) => segment.id === segmentId && segment.type === "TEXT" ? { ...segment, text } : segment),
        }),
      });
      return;
    }

    const newQuestions: QuestionModel[] = [];
    const replacement: NoteCompletionSegment[] = [{ id: segmentId, type: "TEXT", text: parts[0] }];
    let selectedGap = "";
    for (let index = 1; index < parts.length; index += 1) {
      const question = createQuestion(index - 1);
      const gap = { id: crypto.randomUUID(), type: "GAP" as const, question_id: question.id! };
      newQuestions.push(question);
      replacement.push(gap, { id: crypto.randomUUID(), type: "TEXT", text: parts[index] });
      selectedGap = gap.id;
    }
    activeCaret.current = null;
    shortcutKeyUpSource.current = segmentId;
    const trailing = replacement.at(-1)!;
    pendingFocus.current = {
      segmentId: trailing.id,
      offset: trailing.type === "TEXT" ? trailing.text.length : 0,
      preserveGapSelection: true,
    };
    setSelectedGapId(selectedGap);
    commit({
      ...layout,
      blocks: layout.blocks.map((block) => block.id !== blockId ? block : {
        ...block,
        segments: block.segments.flatMap((segment) => segment.id === segmentId ? replacement : [segment]),
      }),
    }, [...group.questions, ...newQuestions]);
  }

  function insertGap() {
    const block = layout.blocks.find((item) => item.id === (activeCaret.current?.blockId ?? activeBlockId)) ?? layout.blocks[0];
    if (!block) return;
    const target = block.segments.find((segment) => segment.id === activeCaret.current?.segmentId && segment.type === "TEXT")
      ?? [...block.segments].reverse().find((segment) => segment.type === "TEXT");
    const question = createQuestion(0);
    const gap = { id: crypto.randomUUID(), type: "GAP" as const, question_id: question.id! };
    const segments = target ? block.segments.flatMap((segment) => {
      if (segment.id !== target.id || segment.type !== "TEXT") return [segment];
      const offset = Math.max(0, Math.min(
        activeCaret.current?.segmentId === segment.id ? activeCaret.current.offset : segment.text.length,
        segment.text.length,
      ));
      return [
        { ...segment, text: segment.text.slice(0, offset) },
        gap,
        { id: crypto.randomUUID(), type: "TEXT" as const, text: segment.text.slice(offset) },
      ];
    }) : [...block.segments, gap, { id: crypto.randomUUID(), type: "TEXT" as const, text: "" }];
    activeCaret.current = null;
    setSelectedGapId(gap.id);
    commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, segments } : item) }, [...group.questions, question]);
  }

  function addBlock(afterIndex = layout.blocks.length - 1, sourceStyle: NoteBlockStyle = "TEXT", indent = 0) {
    const segmentId = crypto.randomUUID();
    const block: NoteCompletionBlock = {
      id: crypto.randomUUID(),
      style: nextBlockStyle(sourceStyle),
      indent,
      segments: [{ id: segmentId, type: "TEXT", text: "" }],
    };
    const blocks = [...layout.blocks];
    blocks.splice(afterIndex + 1, 0, block);
    pendingFocus.current = { segmentId, offset: 0 };
    setActiveBlockId(block.id);
    commit({ ...layout, blocks });
  }

  function moveBlock(index: number, offset: number) {
    const target = index + offset;
    if (target < 0 || target >= layout.blocks.length) return;
    const blocks = [...layout.blocks];
    [blocks[index], blocks[target]] = [blocks[target], blocks[index]];
    commit({ ...layout, blocks });
  }

  function removeGap(segmentId: string, questionId: string) {
    const blocks = layout.blocks.map((block) => ({
      ...block,
      segments: compactSegments(block.segments.filter((segment) => segment.id !== segmentId)),
    }));
    setSelectedGapId("");
    commit({ ...layout, blocks }, group.questions.filter((question) => question.id !== questionId));
  }

  function removeBlock(blockId: string) {
    const block = layout.blocks.find((item) => item.id === blockId);
    if (!block) return;
    const removed = new Set(block.segments.flatMap((segment) => segment.type === "GAP" ? [segment.question_id] : []));
    const blocks = layout.blocks.filter((item) => item.id !== blockId);
    setSelectedGapId("");
    setActiveBlockId(blocks[0]?.id ?? "");
    commit({ ...layout, blocks }, group.questions.filter((question) => !question.id || !removed.has(question.id)));
  }

  function requestBlockRemoval(block: NoteCompletionBlock) {
    const questionNumbers = block.segments.flatMap((segment) => {
      if (segment.type !== "GAP") return [];
      const question = group.questions.find((item) => item.id === segment.question_id);
      return question ? [question.number] : [];
    });
    if (!questionNumbers.length) {
      removeBlock(block.id);
      return;
    }
    setDeleteTarget({ kind: "block", blockId: block.id, questionNumbers });
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
    const segment = parent?.closest<HTMLElement>("[data-note-text-segment]");
    const block = segment?.closest<HTMLElement>("[data-note-block]");
    if (!node || rawOffset === undefined || !segment || !block) return null;
    let offset = rawOffset;
    try {
      const range = document.createRange();
      range.selectNodeContents(segment);
      range.setEnd(node, rawOffset);
      offset = range.toString().length;
    } catch {
      offset = rawOffset;
    }
    return {
      blockId: block.dataset.noteBlock!,
      segmentId: segment.dataset.noteTextSegment!,
      offset: Math.max(0, Math.min(offset, segment.textContent?.length ?? 0)),
      x: clientX,
      y: clientY,
    };
  }

  function dropGap(segmentId: string) {
    if (!segmentId || !dropCaret) return;
    const moving = layout.blocks.flatMap((block) => block.segments).find((segment) => segment.id === segmentId && segment.type === "GAP");
    if (!moving) return;
    const blocks = layout.blocks.map((block) => {
      const without = block.segments.filter((segment) => segment.id !== segmentId);
      const inserted = without.flatMap((segment) => {
        if (block.id !== dropCaret.blockId || segment.id !== dropCaret.segmentId || segment.type !== "TEXT") return [segment];
        const offset = Math.max(0, Math.min(dropCaret.offset, segment.text.length));
        return [
          { ...segment, text: segment.text.slice(0, offset) },
          moving,
          { id: crypto.randomUUID(), type: "TEXT" as const, text: segment.text.slice(offset) },
        ];
      });
      return { ...block, segments: compactSegments(inserted) };
    });
    setDraggedGapId("");
    setDropCaret(null);
    setSelectedGapId(segmentId);
    commit({ ...layout, blocks });
  }

  const selectedGap = layout.blocks.flatMap((block) => block.segments)
    .find((segment) => segment.id === selectedGapId && segment.type === "GAP");
  const selectedQuestion = selectedGap?.type === "GAP"
    ? group.questions.find((question) => question.id === selectedGap.question_id)
    : undefined;
  const accepted = (selectedQuestion?.answer_key.accepted as string[] | undefined) ?? [];

  function updateSelected(patch: Partial<QuestionModel>) {
    if (!selectedQuestion) return;
    onChange({
      ...group,
      questions: group.questions.map((question) => question.id === selectedQuestion.id ? { ...question, ...patch } : question),
    });
  }

  return <>
    <div className="note-completion-authoring space-y-4">
      <section className="matching-section">
        <div className="matching-section-title">
          <div><h3>Note layout</h3><p>Edit the note inline. Type {"{{gap}}"} or use Insert gap.</p></div>
        </div>
        <label className="field-label note-title-field">Note title <span className="font-normal text-[var(--muted)]">(optional)</span>
          <input aria-label="Note title" className="field" maxLength={300} value={layout.title ?? ""} onChange={(event) => commit({ ...layout, title: event.target.value })} onBlur={(event) => commit({ ...layout, title: event.target.value.trim() })} />
        </label>
        {layout.title?.trim() ? <p className="note-completion-title note-completion-builder-title">{layout.title.trim()}</p> : null}
        <div ref={canvas} className={`note-authoring-canvas ${draggedGapId ? "is-dragging" : ""}`}>
          {layout.blocks.map((block, blockIndex) => (
            <article
              key={block.id}
              data-note-block={block.id}
              className={`note-authoring-block note-style-${block.style.toLowerCase()} note-indent-${block.indent} ${activeBlockId === block.id ? "is-selected" : ""}`}
              onDragOver={(event) => {
                if (!draggedGapId) return;
                event.preventDefault();
                const next = resolvePointerCaret(event.clientX, event.clientY);
                setDropCaret(next?.blockId === block.id ? next : null);
              }}
              onDrop={(event) => {
                event.preventDefault();
                dropGap(draggedGapId || event.dataTransfer.getData("text/plain"));
              }}
            >
              <div className="note-block-toolbar" aria-label={`Block ${blockIndex + 1} controls`}>
                <label>Style
                  <select aria-label={`Block ${blockIndex + 1} style`} value={block.style} onChange={(event) => commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, style: event.target.value as NoteBlockStyle } : item) })}>
                    <option value="HEADING">Heading</option><option value="BULLET">Bullet</option><option value="TEXT">Text</option><option value="EXAMPLE">Example</option>
                  </select>
                </label>
                <button type="button" className="icon-button" aria-label={`Decrease block ${blockIndex + 1} indent`} disabled={block.indent === 0} onClick={() => commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, indent: Math.max(0, item.indent - 1) } : item) })}>←</button>
                <button type="button" className="icon-button" aria-label={`Increase block ${blockIndex + 1} indent`} disabled={block.indent === 3} onClick={() => commit({ ...layout, blocks: layout.blocks.map((item) => item.id === block.id ? { ...item, indent: Math.min(3, item.indent + 1) } : item) })}>→</button>
                <button type="button" className="icon-button" aria-label={`Move block ${blockIndex + 1} up`} disabled={blockIndex === 0} onClick={() => moveBlock(blockIndex, -1)}>↑</button>
                <button type="button" className="icon-button" aria-label={`Move block ${blockIndex + 1} down`} disabled={blockIndex === layout.blocks.length - 1} onClick={() => moveBlock(blockIndex, 1)}>↓</button>
                <button type="button" className="btn btn-danger-ghost" aria-label={`Delete block ${blockIndex + 1}`} disabled={layout.blocks.length === 1} onClick={() => requestBlockRemoval(block)}>Delete block</button>
              </div>
              <div
                className="note-authoring-line"
                aria-label={`Note block ${blockIndex + 1} content`}
                onClick={(event) => focusBlockContent(event, block)}
              >
                {block.style === "BULLET" ? <span className="note-completion-marker" aria-hidden="true">•</span> : null}
                <div
                  className="note-authoring-content"
                  data-empty={block.segments.every((segment) => segment.type === "TEXT" && segment.text.length === 0) || undefined}
                >
                  {block.segments.map((segment, segmentIndex) => segment.type === "TEXT" ? (
                    <EditableText
                      key={segment.id}
                      text={segment.text}
                      role="textbox"
                      aria-label={`Note block ${blockIndex + 1} text segment ${segmentIndex + 1}`}
                      contentEditable
                      suppressContentEditableWarning
                      data-note-text-segment={segment.id}
                      className="note-editable-text"
                      onFocus={(event) => {
                        const preserveGapSelection = pendingFocus.current?.segmentId === segment.id
                          && pendingFocus.current.preserveGapSelection;
                        rememberCaret(block.id, segment.id, event.currentTarget, !preserveGapSelection);
                      }}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter") return;
                        event.preventDefault();
                        addBlock(blockIndex, block.style, block.indent);
                      }}
                      onKeyUp={(event) => {
                        if (event.key === "}" && shortcutKeyUpSource.current === segment.id) {
                          shortcutKeyUpSource.current = null;
                          return;
                        }
                        shortcutKeyUpSource.current = null;
                        rememberCaret(block.id, segment.id, event.currentTarget);
                      }}
                      onMouseUp={(event) => rememberCaret(block.id, segment.id, event.currentTarget)}
                      onInput={(event) => {
                        rememberCaret(block.id, segment.id, event.currentTarget);
                        updateText(block.id, segment.id, (event.currentTarget.textContent ?? "").replace(/[\r\n]+/g, " "));
                      }}
                    />
                  ) : (
                    <button
                      key={segment.id}
                      type="button"
                      draggable
                      aria-label={`Note gap question ${group.questions.find((question) => question.id === segment.question_id)?.number ?? "unknown"}`}
                      aria-pressed={selectedGapId === segment.id}
                      className={`completion-gap-token ${selectedGapId === segment.id ? "is-selected" : ""} ${draggedGapId === segment.id ? "is-dragged" : ""}`}
                      onClick={() => { setSelectedGapId(segment.id); setActiveBlockId(block.id); }}
                      onDragStart={(event) => {
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", segment.id);
                        setDraggedGapId(segment.id);
                        setSelectedGapId(segment.id);
                      }}
                      onDragEnd={() => { setDraggedGapId(""); setDropCaret(null); }}
                    >Q{group.questions.find((question) => question.id === segment.question_id)?.number ?? "?"}</button>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
        {dropCaret ? <span className="completion-drop-indicator" style={{ left: dropCaret.x, top: dropCaret.y }} aria-label="Note gap drop position" /> : null}
        <div className="note-layout-actions">
          <button type="button" className="btn btn-primary" onClick={insertGap}>+ Insert gap</button>
          <button type="button" className="btn btn-secondary" onClick={() => addBlock()}>+ Add block</button>
          <span>Type {"{{gap}}"} or use Insert gap</span>
        </div>
      </section>

      {!deleteTarget && selectedGap && selectedQuestion ? (
        <fieldset className="note-gap-inspector" aria-label={`Question ${selectedQuestion.number} note gap inspector`}>
          <div className="note-gap-inspector-heading">
            <div><span className="page-eyebrow">Selected gap</span><h3>Question {selectedQuestion.number}</h3></div>
            <button type="button" className="btn btn-danger-ghost" onClick={() => setDeleteTarget({ kind: "gap", segmentId: selectedGap.id, questionId: selectedQuestion.id! })}>Remove gap</button>
          </div>
          <div className="note-gap-inspector-grid">
            <label className="field-label sm:col-span-2">Correct answer<input aria-label="Correct answer" className="field" value={accepted[0] ?? ""} onChange={(event) => updateSelected({ answer_key: { kind: "TEXT", accepted: [event.target.value, ...accepted.slice(1)], case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })} /></label>
            <div className="sm:col-span-2"><p className="field-label">Alternative answers</p>
              {accepted.slice(1).map((answer, index) => <div key={index} className="mt-2 flex gap-2"><input aria-label={`Alternative answer ${index + 1}`} className="field" value={answer} onChange={(event) => { const next = [...accepted]; next[index + 1] = event.target.value; updateSelected({ answer_key: { kind: "TEXT", accepted: next, case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } }); }} /><button type="button" className="btn btn-danger-ghost" onClick={() => updateSelected({ answer_key: { kind: "TEXT", accepted: accepted.filter((_, answerIndex) => answerIndex !== index + 1), case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })}>Remove</button></div>)}
              <button type="button" className="btn btn-secondary mt-2" onClick={() => updateSelected({ answer_key: { kind: "TEXT", accepted: [...accepted, ""], case_sensitive: Boolean(selectedQuestion.answer_key.case_sensitive) } })}>+ Add alternative answer</button>
            </div>
            <label className="field-label">Maximum words<input type="number" min={1} aria-label="Maximum words" className="field" value={(selectedQuestion.config.max_words as number | undefined) ?? ""} onChange={(event) => updateSelected({ config: { ...selectedQuestion.config, max_words: event.target.value ? Number(event.target.value) : null } })} /></label>
            <label className="field-label">Maximum numbers<input type="number" min={0} aria-label="Maximum numbers" className="field" value={(selectedQuestion.config.max_numbers as number | undefined) ?? ""} onChange={(event) => updateSelected({ config: { ...selectedQuestion.config, max_numbers: event.target.value ? Number(event.target.value) : null } })} /></label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(selectedQuestion.answer_key.case_sensitive)} onChange={(event) => updateSelected({ answer_key: { kind: "TEXT", accepted, case_sensitive: event.target.checked } })} /> Case-sensitive grading</label>
          </div>
        </fieldset>
      ) : !deleteTarget ? <p className="notice">Select a gap to edit its answer key.</p> : null}
    </div>
    <ConfirmDialog open={deleteTarget?.kind === "gap"} title="Remove this gap?" description="The linked question and its answer configuration will also be removed." confirmLabel="Remove gap" pending={false} onCancel={() => setDeleteTarget(null)} onConfirm={() => { if (deleteTarget?.kind === "gap") removeGap(deleteTarget.segmentId, deleteTarget.questionId); setDeleteTarget(null); }} />
    <ConfirmDialog open={deleteTarget?.kind === "block"} title="Remove this note block?" description={deleteTarget?.kind === "block" ? `${questionList(deleteTarget.questionNumbers)} and their answer keys will also be removed.` : ""} confirmLabel="Remove block" pending={false} onCancel={() => setDeleteTarget(null)} onConfirm={() => { if (deleteTarget?.kind === "block") removeBlock(deleteTarget.blockId); setDeleteTarget(null); }} />
  </>;
}
