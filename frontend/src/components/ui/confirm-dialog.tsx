"use client";

import { useEffect, useId, useRef } from "react";
import { useTranslation } from "@/lib/i18n/locale-provider";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  pendingLabel,
  pending,
  errorMessage,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  pendingLabel?: string;
  pending: boolean;
  errorMessage?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement;
    cancelButton.current?.focus();
    return () => {
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !pending) {
        event.preventDefault();
        onCancel();
      }
      if (event.key !== "Tab") return;
      const buttons = panel.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
      if (!buttons?.length) {
        event.preventDefault();
        panel.current?.focus();
        return;
      }
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      const outside = !panel.current?.contains(document.activeElement);
      if (event.shiftKey && (document.activeElement === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, pending, onCancel]);

  if (!open) return null;

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !pending) onCancel(); }}>
      <div
        ref={panel}
        tabIndex={-1}
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-modal="true"
        role="dialog"
        className="dialog-panel"
      >
        <div className="dialog-danger-icon" aria-hidden="true">!</div>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>
          {description}
        </p>
        {errorMessage ? <p role="alert" className="notice notice-error">{errorMessage}</p> : null}
        <div className="dialog-actions">
          <button
            ref={cancelButton}
            type="button"
            disabled={pending}
            onClick={onCancel}
            className="btn btn-secondary"
          >
            {cancelLabel ?? t("common.cancel")}
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={onConfirm}
            className="btn btn-danger"
          >
            {pending ? pendingLabel ?? t("common.working") : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
