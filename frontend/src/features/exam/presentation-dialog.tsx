"use client";

import { useEffect, useEffectEvent, useId, useRef, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "@/lib/i18n/locale-provider";
import type { AttemptPresentationMode } from "./attempt-presentation";
import { PresentationChoice } from "./presentation-choice";
import type { PresentationPreview } from "./presentation-thumbnail";
import styles from "./presentation-choice.module.css";

const focusableSelector = 'button:not([disabled]), input:not([disabled]), [tabindex="0"]';

export function PresentationDialog({ open, module, value, onChange, onClose, onConfirm, pending, error, returnFocusRef, preview }: {
  open: boolean;
  module: "READING" | "LISTENING";
  value: AttemptPresentationMode;
  onChange(value: AttemptPresentationMode): void;
  onClose(): void;
  onConfirm(): void;
  pending: boolean;
  error?: string | null;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
  preview?: PresentationPreview;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const dismiss = useEffectEvent(() => { if (!pending) onClose(); });
  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    const trigger = returnFocusRef.current;
    const shell = document.querySelector<HTMLElement>(".app-shell");
    const wasInert = shell?.hasAttribute("inert") ?? false;
    const previousOverflow = document.body.style.overflow;
    shell?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLInputElement>('input:checked')?.focus();
    function focusableElements() { return [...(panel.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [])].filter(element => !element.matches(":disabled")); }
    function focusInside() { (focusableElements()[0] ?? panel.current)?.focus(); }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); dismiss(); return; }
      if (event.key !== "Tab") return;
      const elements = focusableElements();
      if (!elements.length) { event.preventDefault(); panel.current?.focus(); return; }
      const first = elements[0]; const last = elements[elements.length - 1];
      const outside = !panel.current?.contains(document.activeElement);
      if (event.shiftKey && (outside || document.activeElement === first)) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (outside || document.activeElement === last)) { event.preventDefault(); first.focus(); }
    }
    function keepFocus(event: FocusEvent) { if (event.target instanceof Node && !panel.current?.contains(event.target)) focusInside(); }
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", keepFocus);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", keepFocus);
      if (!wasInert) shell?.removeAttribute("inert");
      document.body.style.overflow = previousOverflow;
      const target = trigger ?? previousFocus;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    };
  }, [open, returnFocusRef]);

  if (!open) return null;
  return createPortal(<div className={styles.backdrop} onMouseDown={event => { if (event.target === event.currentTarget && !pending) onClose(); }}>
    <div ref={panel} className={styles.dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} aria-busy={pending}>
      <header className={styles.header}><div><h2 id={titleId}>{t("presentation.choose")}</h2><p id={descriptionId}>{t("presentation.chooseDescription")}</p></div><button type="button" className="icon-button" disabled={pending} onClick={onClose} aria-label={t("common.close")}>×</button></header>
      <div className={styles.body}><p className={styles.sampleHint}>{t("presentation.sampleHint")}</p><PresentationChoice value={value} onChange={onChange} module={module} disabled={pending} preview={preview} />{error ? <p role="alert" className="notice notice-error">{error}</p> : null}</div>
      <footer className={styles.footer}><button type="button" className="btn btn-secondary" disabled={pending} onClick={onClose}>{t("common.cancel")}</button><button type="button" className="btn btn-primary" disabled={pending} onClick={onConfirm}>{t(pending ? "practice.starting" : "presentation.confirm")}</button></footer>
    </div>
  </div>, document.body);
}
