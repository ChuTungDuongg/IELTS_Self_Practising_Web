"use client";
import { useRef, type ReactNode } from "react";

/** Native disclosure keeps menus keyboard operable without a second focus model. */
export function ActionMenu({ label, children, primary = false }: { label: string; children: ReactNode; primary?: boolean }) {
  const ref = useRef<HTMLDetailsElement>(null);
  return <details ref={ref} className={`classroom-menu${primary ? " classroom-menu-primary" : ""}`} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); ref.current?.removeAttribute("open"); ref.current?.querySelector("summary")?.focus(); }
  }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.removeAttribute("open"); }}>
    <summary>{label}</summary><div onClick={event => { const target = event.target as HTMLElement; if (target.closest("button,a") && !target.closest(".classroom-action") && !(target as HTMLButtonElement).disabled) ref.current?.removeAttribute("open"); }}>{children}</div>
  </details>;
}
