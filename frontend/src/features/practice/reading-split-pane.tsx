"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";
import styles from "./practice-runner.module.css";

const clamp = (value: number, minimum: number, maximum: number) => Math.min(maximum, Math.max(minimum, value));

export function ReadingSplitPane({ id, children }: { id: string; children: [ReactNode, ReactNode] }) {
  const { t } = useTranslation();
  const container = useRef<HTMLDivElement>(null);
  const pointer = useRef<number | null>(null);
  const [ratio, setRatio] = useState(50);
  const [minimum, setMinimum] = useState(30);
  const [dragging, setDragging] = useState(false);
  const maximum = 100 - minimum;
  useEffect(() => {
    if (!container.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width - 12;
      if (width <= 0) return;
      const limit = Math.min(50, Math.max(30, 340 / width * 100));
      setMinimum(limit);
      setRatio(current => clamp(current, limit, 100 - limit));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);

  return <div id={id} ref={container} className={styles.split} data-resizing={dragging || undefined}
    style={{ "--reading-columns": `minmax(0, ${ratio}fr) 12px minmax(0, ${100 - ratio}fr)` } as CSSProperties}>
    {children[0]}
    <div className={styles.separator} role="separator" tabIndex={0} aria-orientation="vertical"
      aria-label={t("practiceUi.resizePanes")} aria-controls={`${id}-questions`}
      aria-valuemin={Math.round(minimum)} aria-valuemax={Math.round(maximum)} aria-valuenow={Math.round(ratio)}
      onPointerDown={event => {
        if (event.button !== 0 || event.isPrimary === false) return;
        event.preventDefault();
        pointer.current = event.pointerId;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        setDragging(true);
      }}
      onPointerMove={event => {
        if (pointer.current === null || pointer.current !== event.pointerId || !container.current) return;
        const bounds = container.current.getBoundingClientRect();
        if (bounds.width <= 12) return;
        setRatio(clamp((event.clientX - bounds.left - 6) / (bounds.width - 12) * 100, minimum, maximum));
      }}
      onPointerUp={event => {
        if (event.pointerId !== pointer.current) return;
        pointer.current = null;
        setDragging(false);
        if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={() => { pointer.current = null; setDragging(false); }}
      onLostPointerCapture={() => { pointer.current = null; setDragging(false); }}
      onKeyDown={event => {
        const step = event.shiftKey ? 10 : 2;
        const next = event.key === "ArrowLeft" ? ratio - step : event.key === "ArrowRight" ? ratio + step
          : event.key === "Home" ? minimum : event.key === "End" ? maximum : event.key === "Enter" ? 50 : null;
        if (next === null) return;
        event.preventDefault();
        setRatio(clamp(next, minimum, maximum));
      }}
    ><span aria-hidden="true" /></div>
    {children[1]}
  </div>;
}
