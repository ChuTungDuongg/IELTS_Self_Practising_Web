"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { snapToWordBoundaries } from "./word-boundaries";
import type { Highlight, HighlightCreate, HighlightTarget } from "@/lib/api/exam";

export type HighlightController = {
  highlights: Highlight[];
  onCreate?: (body: HighlightCreate) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  readOnly?: boolean;
};

type PendingSelection = {
  start: number;
  end: number;
  selected_text: string;
  x: number;
  y: number;
};

const POPOVER_EVENT = "ielts-highlight-popover-open";

export function SelectableText({ text, target, controller, className }: {
  text: string;
  target: HighlightTarget;
  controller?: HighlightController;
  className?: string;
}) {
  const root = useRef<HTMLSpanElement>(null);
  const createPopover = useRef<HTMLDivElement>(null);
  const removePopover = useRef<HTMLDivElement>(null);
  const instanceId = useRef(crypto.randomUUID());
  const [pending, setPending] = useState<PendingSelection | null>(null);
  const [activeHighlight, setActiveHighlight] = useState<(Highlight & { x: number; y: number }) | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const matches = (controller?.highlights ?? [])
    .filter((item) => item.target_kind === target.target_kind
      && item.target_id === target.target_id
      && (item.segment_id ?? null) === (target.segment_id ?? null))
    .sort((a, b) => a.start_offset - b.start_offset);

  useEffect(() => {
    if (!pending && !activeHighlight) return;
    const dismiss = (event: PointerEvent) => {
      const node = event.target as Node;
      if (!createPopover.current?.contains(node) && !removePopover.current?.contains(node)) {
        setPending(null);
        setActiveHighlight(null);
        setError("");
      }
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPending(null);
        setActiveHighlight(null);
        setError("");
      }
    };
    const closePeer = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== instanceId.current) {
        setPending(null);
        setActiveHighlight(null);
        setError("");
      }
    };
    const closeOnScroll = (event: Event) => {
      if (event.target instanceof Node && (createPopover.current?.contains(event.target) || removePopover.current?.contains(event.target))) return;
      setPending(null);
      setActiveHighlight(null);
    };
    document.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("resize", closeOnScroll);
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    document.addEventListener(POPOVER_EVENT, closePeer);
    return () => {
      document.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("resize", closeOnScroll);
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
      document.removeEventListener(POPOVER_EVENT, closePeer);
    };
  }, [activeHighlight, pending]);

  function announcePopover() {
    document.dispatchEvent(new CustomEvent(POPOVER_EVENT, { detail: instanceId.current }));
  }

  function select() {
    if (controller?.readOnly || !controller?.onCreate || !root.current) return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) {
      setPending(null);
      return;
    }
    const range = selection.getRangeAt(0);
    if (!root.current.contains(range.startContainer) || !root.current.contains(range.endContainer)) {
      setPending(null);
      return;
    }
    const beforeStart = range.cloneRange();
    beforeStart.selectNodeContents(root.current);
    beforeStart.setEnd(range.startContainer, range.startOffset);
    const beforeEnd = range.cloneRange();
    beforeEnd.selectNodeContents(root.current);
    beforeEnd.setEnd(range.endContainer, range.endOffset);
    const [start, end] = snapToWordBoundaries(
      text,
      beforeStart.toString().length,
      beforeEnd.toString().length,
    );
    if (start >= end || matches.some((item) => start < item.end_offset && end > item.start_offset)) {
      setPending(null);
      return;
    }
    const rect = range.getBoundingClientRect();
    announcePopover();
    setActiveHighlight(null);
    setError("");
    setPending({
      start,
      end,
      selected_text: text.slice(start, end),
      x: rect.left + rect.width / 2,
      y: rect.top - 8,
    });
  }

  function openHighlight(item: Highlight, element: HTMLElement) {
    if (controller?.readOnly || !controller?.onDelete) return;
    const selection = window.getSelection();
    if (selection && !selection.isCollapsed) return;
    const rect = element.getBoundingClientRect();
    announcePopover();
    setPending(null);
    setError("");
    setActiveHighlight({ ...item, x: rect.left + rect.width / 2, y: rect.bottom + 8 });
  }

  const content: React.ReactNode[] = [];
  let cursor = 0;
  for (const item of matches) {
    if (item.start_offset < cursor || item.end_offset > text.length) continue;
    content.push(text.slice(cursor, item.start_offset));
    const mutable = Boolean(controller?.onDelete && !controller.readOnly);
    content.push(<mark
      key={item.id}
      className={mutable ? "highlight-mark highlight-mark-interactive" : "highlight-mark"}
      role={mutable ? "button" : undefined}
      tabIndex={mutable ? 0 : undefined}
      aria-label={mutable ? `Highlight: ${item.selected_text}. Open options` : undefined}
      onClick={(event) => openHighlight(item, event.currentTarget)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openHighlight(item, event.currentTarget);
        }
      }}
    >{text.slice(item.start_offset, item.end_offset)}</mark>);
    cursor = item.end_offset;
  }
  content.push(text.slice(cursor));

  return <span className={className}>
    <span ref={root} onMouseUp={select} onTouchEnd={select} data-highlight-target>{content}</span>
    {pending && typeof document !== "undefined" ? createPortal(<div ref={createPopover} className="highlight-popover highlight-create-popover" style={{ left: pending.x, top: pending.y }} role="dialog" aria-label="Create highlight">
      <q>{pending.selected_text}</q>
      <button type="button" disabled={working} onClick={async () => {
        setWorking(true);
        setError("");
        try {
          await controller?.onCreate?.({
            ...target,
            start_offset: pending.start,
            end_offset: pending.end,
            selected_text: pending.selected_text,
          });
          setPending(null);
          window.getSelection()?.removeAllRanges();
        } catch {
          setError("Could not create the highlight. Please try again.");
        } finally {
          setWorking(false);
        }
      }}>{working ? "Working…" : "Highlight"}</button>
      {error ? <p role="alert">{error}</p> : null}
    </div>, document.body) : null}
    {activeHighlight && typeof document !== "undefined" ? createPortal(<div ref={removePopover} className="highlight-popover highlight-remove-popover" style={{ left: activeHighlight.x, top: activeHighlight.y }} role="dialog" aria-label="Highlight options">
      <p>Highlight</p>
      <q>{activeHighlight.selected_text}</q>
      <button type="button" className="highlight-remove-action" disabled={working} onClick={async () => {
        setWorking(true);
        setError("");
        try {
          await controller?.onDelete?.(activeHighlight.id);
          setActiveHighlight(null);
        } catch {
          setError("Could not remove the highlight. Please try again.");
        } finally {
          setWorking(false);
        }
      }}>{working ? "Removing…" : "Remove highlight"}</button>
      {error ? <p role="alert">{error}</p> : null}
    </div>, document.body) : null}
  </span>;
}
