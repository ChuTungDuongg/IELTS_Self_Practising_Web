"use client";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { PlusIcon } from "@/components/ui/icons";
import { useAssignmentsText } from "./messages";

const query = "(max-width: 767px)";
function subscribe(change: () => void) { const media = window.matchMedia?.(query); media?.addEventListener("change", change); return () => media?.removeEventListener("change", change); }
const snapshot = () => window.matchMedia?.(query).matches ?? false;
const serverSnapshot = () => false;

export function AssignmentCreationPanel({ children, request = 0 }: { children: ReactNode; request?: number }) {
  const { at } = useAssignmentsText(), compact = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  const [open, setOpen] = useState(false), root = useRef<HTMLElement>(null);
  const expanded = !compact || open;
  useEffect(() => {
    if (!request) return;
    // Header requests reveal the one form and focus its first control.
    const frame = requestAnimationFrame(() => { setOpen(true); requestAnimationFrame(() => {
      root.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
      root.current?.querySelector<HTMLElement>("#assignment-creation-fields select, #assignment-creation-fields input, #assignment-creation-fields button")?.focus({ preventScroll: true });
    }); });
    return () => cancelAnimationFrame(frame);
  }, [request]);
  return <aside ref={root} className="assignments-creation" aria-label={at("new")}>
    {compact ? <button type="button" className="btn btn-primary assignments-create-toggle" aria-expanded={expanded} aria-controls="assignment-creation-fields" onClick={() => setOpen(value => !value)}><PlusIcon />{at("create")}</button> : null}
    <div id="assignment-creation-fields" hidden={!expanded}>{children}</div>
  </aside>;
}
