"use client";

import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type WritingAnnotation } from "@/lib/api/writing-ai";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationFunction } from "@/lib/i18n/types";
import { presentAIFeedback } from "./ai-feedback-presentation";
import styles from "./annotated-essay.module.css";

const severity = { ERROR: 0, LIMITATION: 1, OPTIONAL_REFINEMENT: 2 };
const noAnnotations: WritingAnnotation[] = [];
const viewportMargin = 14;
const anchorGap = 8;

/** Keep paragraph and separator ranges in the original UTF-16 coordinate space. */
function essayRanges(content: string) {
  const ranges: { start: number; end: number; separator: boolean }[] = [];
  let start = 0;
  for (const match of content.matchAll(/(?:\r\n|\r|\n)+/g)) {
    if (start < match.index) ranges.push({ start, end: match.index, separator: false });
    start = match.index + match[0].length;
    ranges.push({ start: match.index, end: start, separator: true });
  }
  if (start < content.length) ranges.push({ start, end: content.length, separator: false });
  return ranges;
}

/** Defensive display validation. Backend alone resolves and judges the issue. */
export function validEssayAnnotations(content: string, annotations: WritingAnnotation[]) {
  const seen = new Set<string>();
  const counts = { gra: 0, lr: 0 };
  return [...annotations].sort((a, b) => a.start_offset - b.start_offset || a.end_offset - b.end_offset || a.id.localeCompare(b.id)).filter(annotation => {
    const { criterion, start_offset: start, end_offset: end } = annotation;
    if ((criterion !== "gra" && criterion !== "lr") || seen.has(annotation.id)
      || !Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > content.length
      || content.slice(start, end) !== annotation.original_span
      || (annotation.kind === "ERROR" && annotation.confidence !== "HIGH")
      || counts[criterion] >= 4) return false;
    seen.add(annotation.id); counts[criterion] += 1;
    return true;
  });
}

export function annotationHeading(annotation: WritingAnnotation, t: TranslationFunction) {
  const category = annotation.category;
  const label = annotation.criterion === "gra"
    ? t(category === "punctuation" ? "writingAI.punctuation" : "writingAI.grammar")
    : t(category === "spelling" ? "writingAI.spelling" : category === "word_formation" ? "writingAI.wordFormation"
      : category === "word_choice" ? "writingAI.wordChoice" : category === "collocation" ? "writingAI.collocation"
      : category === "lexical_precision" ? "writingAI.lexicalPrecision" : "writingAI.vocabulary");
  return `${annotation.criterion.toUpperCase()} · ${label}`;
}

export function AnnotationDetails({ annotation }: { annotation: WritingAnnotation }) {
  const { t } = useTranslation();
  return <div className={styles.details}>
    <strong>{annotationHeading(annotation, t)}</strong>
    <small>{t(annotation.kind === "ERROR" ? "writingAI.error" : annotation.kind === "LIMITATION" ? "writingAI.limitation" : "writingAI.optionalRefinement")}</small>
    <p className={styles.original}>{annotation.original_span}</p>
    {annotation.suggested_revision ? <p className={styles.revision}><span>{t("writingAI.suggestedRevision")}</span> → <span>{annotation.suggested_revision}</span></p> : null}
    <p>{presentAIFeedback(annotation.message)}</p>
  </div>;
}

export function AnnotatedEssay({ content, annotations = noAnnotations, onViewFeedback }: {
  content: string; annotations?: WritingAnnotation[]; onViewFeedback?: (id: string) => void;
}) {
  const { t } = useTranslation();
  const popoverId = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLSpanElement | null>(null);
  const popover = useRef<HTMLElement | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [opened, setOpened] = useState<{ key: string; pinned: boolean } | null>(null);
  const ranges = useMemo(() => essayRanges(content), [content]);
  const segments = useMemo(() => {
    const accepted = validEssayAnnotations(content, annotations);
    const boundaries = [...new Set([0, content.length, ...ranges.flatMap(range => [range.start, range.end]),
      ...accepted.flatMap(annotation => [annotation.start_offset, annotation.end_offset])])].sort((a, b) => a - b);
    return boundaries.slice(0, -1).map((start, index) => {
      const end = boundaries[index + 1];
      const issues = accepted.filter(annotation => annotation.start_offset <= start && annotation.end_offset >= end)
        .sort((a, b) => severity[a.kind] - severity[b.kind] || a.id.localeCompare(b.id));
      return { start, end, key: `${start}:${end}:${issues.map(issue => issue.id).join(":")}`, text: content.slice(start, end), issues };
    });
  }, [content, annotations, ranges]);
  const current = segments.find(segment => segment.key === opened?.key);
  const pinned = Boolean(current && opened?.pinned);

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);
  const close = useCallback(() => {
    cancelClose();
    if (popover.current?.contains(document.activeElement)) trigger.current?.focus();
    setOpened(null);
  }, [cancelClose]);

  useEffect(() => cancelClose, [cancelClose]);

  useLayoutEffect(() => {
    if (!current || !trigger.current || !popover.current) return;
    const anchor = trigger.current;
    const floating = popover.current;
    function reposition() {
      const viewport = window.visualViewport;
      const leftEdge = (viewport?.offsetLeft ?? 0) + viewportMargin;
      const topEdge = (viewport?.offsetTop ?? 0) + viewportMargin;
      const rightEdge = (viewport?.offsetLeft ?? 0) + (viewport?.width ?? window.innerWidth) - viewportMargin;
      const bottomEdge = (viewport?.offsetTop ?? 0) + (viewport?.height ?? window.innerHeight) - viewportMargin;
      const width = Math.max(0, Math.min(360, rightEdge - leftEdge));
      floating.style.width = `${width}px`;
      const bounds = anchor.getBoundingClientRect();
      const measured = floating.getBoundingClientRect();
      // scrollHeight retains the full content height when the panel is constrained.
      const naturalHeight = Math.max(measured.height, floating.scrollHeight + floating.offsetHeight - floating.clientHeight);
      const below = Math.max(0, bottomEdge - bounds.bottom - anchorGap);
      const above = Math.max(0, bounds.top - topEdge - anchorGap);
      const flip = naturalHeight > below && above > below;
      const available = flip ? above : below;
      const maxHeight = Math.max(0, Math.min(bottomEdge - topEdge, available || bottomEdge - topEdge));
      const height = Math.min(naturalHeight, maxHeight);
      const desiredTop = flip ? bounds.top - anchorGap - height : bounds.bottom + anchorGap;
      const desiredLeft = getComputedStyle(anchor).direction === "rtl" ? bounds.right - width : bounds.left;
      floating.style.left = `${Math.max(leftEdge, Math.min(desiredLeft, rightEdge - width))}px`;
      floating.style.top = `${Math.max(topEdge, Math.min(desiredTop, bottomEdge - height))}px`;
      floating.style.maxHeight = `${maxHeight}px`;
      floating.style.visibility = "visible";
      floating.dataset.placement = flip ? "above" : "below";
    }
    reposition();
    window.addEventListener("resize", reposition);
    // Capture also observes scrolling inside essay/review containers.
    window.addEventListener("scroll", reposition, true);
    window.visualViewport?.addEventListener("resize", reposition);
    window.visualViewport?.addEventListener("scroll", reposition);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(reposition);
    observer?.observe(floating);
    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); close(); }
    }
    document.addEventListener("keydown", onEscape);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      window.visualViewport?.removeEventListener("resize", reposition);
      window.visualViewport?.removeEventListener("scroll", reposition);
      observer?.disconnect();
      document.removeEventListener("keydown", onEscape);
    };
  }, [current, close]);

  function open(key: string, element: HTMLSpanElement, pinned: boolean) {
    cancelClose();
    trigger.current = element;
    setOpened(previous => ({ key, pinned: pinned || (previous?.key === key && previous.pinned) || false }));
  }
  function isInside(target: EventTarget | null) {
    return target instanceof Node && (root.current?.contains(target) || popover.current?.contains(target));
  }
  function leave(target: EventTarget | null) {
    if (pinned || isInside(target)) return;
    cancelClose();
    // Let the pointer cross the small gap between the anchor and portal.
    closeTimer.current = setTimeout(() => setOpened(null), 160);
  }

  return <div ref={root} className={styles.root} onMouseEnter={cancelClose} onMouseLeave={event => leave(event.relatedTarget)}
    onBlur={event => { if (!pinned && !isInside(event.relatedTarget)) close(); }}>
    <div data-essay-text className={styles.essay}>{ranges.map(range => range.separator
      // Hidden separators preserve exact textContent without adding visual blank lines.
      ? <span key={range.start} hidden className={styles.separator}>{content.slice(range.start, range.end)}</span>
      : <p key={range.start} className={styles.paragraph}>{segments.filter(segment => segment.start >= range.start && segment.end <= range.end).map(segment => segment.issues.length
      ? <span key={segment.key} role="button" tabIndex={0} className={styles.annotation}
        data-severity={segment.issues[0].kind} data-annotation-ids={segment.issues.map(issue => issue.id).join(" ")}
        aria-label={`${t("writingAI.suggestionCount", { count: segment.issues.length })}: ${segment.text}`}
        aria-haspopup="dialog" aria-expanded={current?.key === segment.key} aria-controls={current?.key === segment.key ? popoverId : undefined}
        aria-describedby={current?.key === segment.key ? popoverId : undefined}
        onMouseEnter={event => { if (!pinned) open(segment.key, event.currentTarget, false); }} onFocus={event => open(segment.key, event.currentTarget, false)}
        onClick={event => open(segment.key, event.currentTarget, true)}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(segment.key, event.currentTarget, true); } }}>
        {segment.text}
      </span> : segment.text)}</p>)}</div>
    {current ? createPortal(<aside ref={popover} id={popoverId} role="dialog" aria-label={t("writingAI.suggestionCount", { count: current.issues.length })}
      className={styles.popover} onMouseEnter={cancelClose} onMouseLeave={event => leave(event.relatedTarget)}>
      <button type="button" className={styles.close} aria-label={t("writingAI.closeSuggestions")} onClick={close}>×</button>
      {current.issues.map(annotation => <div key={annotation.id}><AnnotationDetails annotation={annotation} />
        {onViewFeedback ? <button type="button" className={styles.navigation} onClick={() => onViewFeedback(annotation.id)}>{t("writingAI.viewFeedback")}</button> : null}
      </div>)}
    </aside>, document.body) : null}
  </div>;
}
