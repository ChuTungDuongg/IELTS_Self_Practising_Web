"use client";
import { useRef, type ReactNode } from "react";
import { MoreIcon } from "@/components/ui/icons";

/** Native disclosure keeps menus keyboard operable without a second focus model. */
export function ActionMenu({ label, children, primary = false, iconOnly = false }: { label: string; children: ReactNode; primary?: boolean; iconOnly?: boolean }) {
  const ref = useRef<HTMLDetailsElement>(null);
  return <details ref={ref} className={`classroom-menu${primary ? " classroom-menu-primary" : ""}`} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); ref.current?.removeAttribute("open"); ref.current?.querySelector("summary")?.focus(); }
  }} onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.removeAttribute("open"); }}>
    <summary className={iconOnly ? "classroom-menu-icon" : undefined}>{iconOnly ? <><MoreIcon width={18} height={18} /><span className="sr-only">{label}</span></> : label}</summary><div onClick={event => { const target = event.target as HTMLElement; if (target.closest("button,a") && !target.closest(".classroom-action") && !(target as HTMLButtonElement).disabled) ref.current?.removeAttribute("open"); }}>{children}</div>
  </details>;
}
