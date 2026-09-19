"use client";

import { useEffect, useRef, useState } from "react";
import { snapToWordBoundaries } from "./word-boundaries";
import type { Highlight, HighlightCreate, HighlightTarget } from "@/lib/api/exam";

export type HighlightController = {
  highlights: Highlight[];
  onCreate?: (body: HighlightCreate) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  readOnly?: boolean;
};

export function SelectableText({ text, target, controller, className }: {
  text: string;
  target: HighlightTarget;
  controller?: HighlightController;
  className?: string;
}) {
  const root = useRef<HTMLSpanElement>(null);
  const popover = useRef<HTMLButtonElement>(null);
  const [pending, setPending] = useState<{ start: number; end: number; selected_text: string; x: number; y: number } | null>(null);
  const matches = (controller?.highlights ?? []).filter((item) => item.target_kind === target.target_kind && item.target_id === target.target_id && (item.segment_id ?? null) === (target.segment_id ?? null)).sort((a, b) => a.start_offset - b.start_offset);

  useEffect(() => {
    if (!pending) return;
    const dismiss = (event: PointerEvent) => { if (!popover.current?.contains(event.target as Node)) setPending(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setPending(null); };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", dismiss); document.removeEventListener("keydown", escape); };
  }, [pending]);

  function select() {
    if (controller?.readOnly || !controller?.onCreate || !root.current) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) { setPending(null); return; }
    const range = selection.getRangeAt(0);
    if (!root.current.contains(range.startContainer) || !root.current.contains(range.endContainer)) { setPending(null); return; }
    const beforeStart = range.cloneRange(); beforeStart.selectNodeContents(root.current); beforeStart.setEnd(range.startContainer, range.startOffset);
    const beforeEnd = range.cloneRange(); beforeEnd.selectNodeContents(root.current); beforeEnd.setEnd(range.endContainer, range.endOffset);
    const [start, end] = snapToWordBoundaries(text, beforeStart.toString().length, beforeEnd.toString().length);
    if (start >= end) { setPending(null); return; }
    const rect = range.getBoundingClientRect();
    setPending({ start, end, selected_text: text.slice(start, end), x: rect.left + rect.width / 2, y: rect.top - 8 });
  }

  const content: React.ReactNode[] = [];
  let cursor = 0;
  for (const item of matches) {
    if (item.start_offset < cursor || item.end_offset > text.length) continue;
    content.push(text.slice(cursor, item.start_offset));
    content.push(<mark key={item.id} className={controller?.onDelete && !controller.readOnly ? "cursor-pointer bg-yellow-200 text-slate-950" : "bg-yellow-200 text-slate-950"} onClick={() => { if (controller?.onDelete && !controller.readOnly && window.confirm("Remove this highlight?")) void controller.onDelete(item.id); }}>{text.slice(item.start_offset, item.end_offset)}</mark>);
    cursor = item.end_offset;
  }
  content.push(text.slice(cursor));

  return <span className={className}>
    <span ref={root} onMouseUp={select} onTouchEnd={select} data-highlight-target>{content}</span>
    {pending ? <button ref={popover} type="button" className="highlight-popover" style={{ left: pending.x, top: pending.y }} onClick={async () => { await controller?.onCreate?.({ ...target, start_offset: pending.start, end_offset: pending.end, selected_text: pending.selected_text }); setPending(null); window.getSelection()?.removeAllRanges(); }}>Highlight</button> : null}
  </span>;
}
