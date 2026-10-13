"use client";

import { useId, useMemo, useRef, useState } from "react";
import { type WritingAnnotation } from "@/lib/api/writing-ai";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationFunction } from "@/lib/i18n/types";
import { presentAIFeedback } from "./ai-feedback-presentation";
import styles from "./annotated-essay.module.css";

const severity = { ERROR: 0, LIMITATION: 1, OPTIONAL_REFINEMENT: 2 };
const noAnnotations: WritingAnnotation[] = [];

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
  const [opened, setOpened] = useState<{ key: string; pinned: boolean; top: number } | null>(null);
  const segments = useMemo(() => {
    const accepted = validEssayAnnotations(content, annotations);
    const boundaries = [...new Set([0, content.length, ...accepted.flatMap(annotation => [annotation.start_offset, annotation.end_offset])])].sort((a, b) => a - b);
    return boundaries.slice(0, -1).map((start, index) => {
      const end = boundaries[index + 1];
      const issues = accepted.filter(annotation => annotation.start_offset <= start && annotation.end_offset >= end)
        .sort((a, b) => severity[a.kind] - severity[b.kind] || a.id.localeCompare(b.id));
      return { key: `${start}:${end}:${issues.map(issue => issue.id).join(":")}`, text: content.slice(start, end), issues };
    });
  }, [content, annotations]);
  const current = segments.find(segment => segment.key === opened?.key);
  const pinned = Boolean(current && opened?.pinned);

  function open(key: string, element: HTMLSpanElement, pinned: boolean) {
    trigger.current = element;
    setOpened(previous => ({ key, pinned: pinned || (previous?.key === key && previous.pinned) || false, top: element.offsetTop + element.offsetHeight + 8 }));
  }
  function close() {
    if (root.current?.contains(document.activeElement) && document.activeElement !== trigger.current) trigger.current?.focus();
    setOpened(null);
  }

  return <div ref={root} className={styles.root} onMouseLeave={() => { if (!pinned) setOpened(null); }}
    onBlur={event => { if (!pinned && !event.currentTarget.contains(event.relatedTarget)) setOpened(null); }}
    onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); close(); } }}>
    <p data-essay-text className={styles.essay}>{segments.map(segment => segment.issues.length
      ? <span key={segment.key} role="button" tabIndex={0} className={styles.annotation}
        data-severity={segment.issues[0].kind} data-annotation-ids={segment.issues.map(issue => issue.id).join(" ")}
        aria-label={`${t("writingAI.suggestionCount", { count: segment.issues.length })}: ${segment.text}`}
        aria-haspopup="dialog" aria-expanded={current?.key === segment.key} aria-controls={current?.key === segment.key ? popoverId : undefined}
        aria-describedby={current?.key === segment.key ? popoverId : undefined}
        onMouseEnter={event => { if (!pinned) open(segment.key, event.currentTarget, false); }} onFocus={event => open(segment.key, event.currentTarget, false)}
        onClick={event => open(segment.key, event.currentTarget, true)}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(segment.key, event.currentTarget, true); } }}>
        {segment.text}
      </span> : segment.text)}</p>
    {current ? <aside id={popoverId} role="dialog" aria-label={t("writingAI.suggestionCount", { count: current.issues.length })}
      className={styles.popover} style={{ top: opened?.top }}>
      <button type="button" className={styles.close} aria-label={t("writingAI.closeSuggestions")} onClick={close}>×</button>
      {current.issues.map(annotation => <div key={annotation.id}><AnnotationDetails annotation={annotation} />
        {onViewFeedback ? <button type="button" className={styles.navigation} onClick={() => onViewFeedback(annotation.id)}>{t("writingAI.viewFeedback")}</button> : null}
      </div>)}
    </aside> : null}
  </div>;
}
