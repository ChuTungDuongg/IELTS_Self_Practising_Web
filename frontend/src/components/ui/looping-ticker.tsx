"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** Each identical copy must be wider than the viewport before translating by half the track. */
export function tickerLayout(viewportWidth: number, unitWidth: number) {
  if (viewportWidth <= 0 || unitWidth <= 0) return { repeats: 8, duration: 26 };
  const repeats = Math.max(2, Math.ceil(viewportWidth / unitWidth) + 1);
  return { repeats, duration: repeats * unitWidth / 48 };
}

export function LoopingTicker({ children }: { children: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const unit = useRef<HTMLSpanElement>(null);
  const [layout, setLayout] = useState({ repeats: 8, duration: 26 });

  useEffect(() => {
    const element = viewport.current, sample = unit.current;
    if (!element || !sample) return;
    let disposed = false;
    const measure = () => {
      if (disposed) return;
      const next = tickerLayout(element.clientWidth, sample.getBoundingClientRect().width);
      setLayout(previous => previous.repeats === next.repeats && Math.abs(previous.duration - next.duration) < .01 ? previous : next);
    };
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element); observer?.observe(sample);
    window.addEventListener("resize", measure);
    void document.fonts?.ready.then(measure);
    measure();
    return () => { disposed = true; observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  return <div ref={viewport} className="gravity-footer-ticker" aria-hidden="true" style={{ "--ticker-duration": `${layout.duration}s` } as CSSProperties}>
    <div className="gravity-footer-ticker-track">
      {[0, 1].map(copy => <div key={copy} className="gravity-footer-ticker-group">
        {Array.from({ length: layout.repeats }, (_, index) => <span ref={copy === 0 && index === 0 ? unit : undefined} className="gravity-footer-ticker-unit" key={index}>{children}</span>)}
      </div>)}
    </div>
  </div>;
}
