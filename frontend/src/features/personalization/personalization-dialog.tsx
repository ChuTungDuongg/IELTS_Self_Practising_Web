"use client";

import { useEffect, useId, useRef, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { PersonalizationControls } from "./personalization-settings";

const focusableSelector = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function PersonalizationDialog({ open, onClose, returnFocusRef }: { open: boolean; onClose(): void; returnFocusRef: RefObject<HTMLButtonElement | null> }) {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    const shell = document.querySelector<HTMLElement>(".app-shell");
    const trigger = returnFocusRef.current;
    const wasInert = shell?.hasAttribute("inert") ?? false;
    const previousOverflow = document.body.style.overflow;
    shell?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = panel.current?.querySelectorAll<HTMLElement>(focusableSelector);
      if (!focusable?.length) {
        event.preventDefault();
        panel.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !panel.current?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !panel.current?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }
    function keepFocus(event: FocusEvent) {
      if (event.target instanceof Node && !panel.current?.contains(event.target)) closeButton.current?.focus();
    }
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", keepFocus);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", keepFocus);
      if (!wasInert) shell?.removeAttribute("inert");
      document.body.style.overflow = previousOverflow;
      const returnFocus = trigger ?? previousFocus;
      if (returnFocus instanceof HTMLElement && returnFocus.isConnected) returnFocus.focus();
    };
  }, [open, onClose, returnFocusRef]);

  if (!open) return null;
  return createPortal(
    <div className="personalization-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} className="personalization-dialog">
        <div className="personalization-dialog-header">
          <div><h2 id={titleId}>{t("personalization.title")}</h2><p id={descriptionId}>{t("personalization.description")}</p></div>
          <button ref={closeButton} type="button" className="icon-button" aria-label={t("personalization.close")} onClick={onClose}>×</button>
        </div>
        <div className="personalization-dialog-body"><PersonalizationControls /></div>
      </div>
    </div>, document.body,
  );
}
