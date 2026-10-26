"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import styles from "./presentation-choice.module.css";

const desktopWidth = 1440;
const desktopHeight = 900;
const emptyDocument = '<!doctype html><html><head></head><body inert></body></html>';

/** A real desktop viewport prevents the page's media queries and selectors distorting a thumbnail. */
export function PreviewViewport({ children, title }: { children: ReactNode; title: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [target, setTarget] = useState<Document | null>(null);
  const [scale, setScale] = useState(.25);
  useEffect(() => {
    const element = container.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => { if (entry.contentRect.width > 0) setScale(entry.contentRect.width / desktopWidth); });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!target) return;
    function syncStyles() {
      if (!target) return;
      for (const attribute of document.documentElement.attributes) target.documentElement.setAttribute(attribute.name, attribute.value);
      target.head.querySelectorAll("[data-preview-style]").forEach(element => element.remove());
      document.head.querySelectorAll('link[rel="stylesheet"], style').forEach(element => {
        const clone = element.cloneNode(true) as HTMLElement;
        clone.setAttribute("data-preview-style", ""); target.head.appendChild(clone);
      });
      const style = target.createElement("style");
      style.setAttribute("data-preview-style", "");
      style.textContent = "html,body{margin:0;width:100%;height:100%;overflow:hidden}body{pointer-events:none}";
      target.head.appendChild(style);
    }
    syncStyles();
    const theme = new MutationObserver(syncStyles);
    theme.observe(document.documentElement, { attributes: true });
    const stylesObserver = new MutationObserver(syncStyles);
    stylesObserver.observe(document.head, { childList: true, subtree: true, characterData: true });
    return () => { theme.disconnect(); stylesObserver.disconnect(); };
  }, [target]);
  return <div ref={container} className={styles.thumbnail} aria-hidden="true" inert>
    <iframe title={title} srcDoc={emptyDocument} sandbox="allow-same-origin" tabIndex={-1} className={styles.previewFrame}
      style={{ width: desktopWidth, height: desktopHeight, transform: `scale(${scale})` }}
      onLoad={event => { const doc = event.currentTarget.contentDocument; if (doc?.body) { doc.body.setAttribute("inert", ""); setTarget(doc); } }} />
    {target ? createPortal(children, target.body) : null}
  </div>;
}
