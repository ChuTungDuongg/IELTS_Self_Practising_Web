"use client";

import { useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import { useContentTranslation, type ContentMessage } from "./content-messages";

export function contentError(error: unknown, fallback: string) { return error instanceof ApiError ? error.message : fallback; }
export function contentActionError(error: unknown, ct: (key: ContentMessage) => string) {
  const messages: Partial<Record<string, ContentMessage>> = {
    CLASSROOM_ARCHIVED: "archivedRoom", CLASSROOM_CAPABILITY_REQUIRED: "permissionRequired", CLASSROOM_OWNERSHIP_REQUIRED: "permissionRequired",
    CLASSROOM_OBSERVER_READ_ONLY: "readOnly",
    ASSIGNMENT_NOT_ACCESSIBLE: "assignmentUnavailable", ASSIGNMENT_NOT_FOUND: "assignmentUnavailable",
  };
  const message = error instanceof ApiError ? messages[error.code] : undefined;
  return message ? ct(message) : contentError(error, ct("error"));
}
export function ContentAction({ children, action, onDone, confirm, disabled = false }: {
  children: React.ReactNode; action: () => Promise<unknown>; onDone?: () => Promise<unknown> | void;
  confirm?: { title: string; description: string }; disabled?: boolean;
}) {
  const { ct } = useContentTranslation();
  const [open, setOpen] = useState(false), [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null);
  const running = useRef(false);
  async function run() {
    if (running.current) return; running.current = true; setPending(true); setError(null);
    try { await action(); await onDone?.(); setOpen(false); }
    catch (caught) { setError(contentActionError(caught, ct)); }
    finally { running.current = false; setPending(false); }
  }
  return <span className="classroom-action">
    <button type="button" className="btn btn-secondary" disabled={disabled || pending} onClick={() => confirm ? setOpen(true) : void run()}>{pending ? ct("working") : children}</button>
    {error && !open ? <span role="alert" className="notice notice-error">{error}</span> : null}
    {confirm ? <ConfirmDialog open={open} title={confirm.title} description={confirm.description} confirmLabel={typeof children === "string" ? children : ct("save")} cancelLabel={ct("cancel")} pendingLabel={ct("working")} pending={pending} errorMessage={error ?? undefined} onCancel={() => setOpen(false)} onConfirm={() => void run()} /> : null}
  </span>;
}
