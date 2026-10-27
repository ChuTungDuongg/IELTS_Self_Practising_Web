"use client";

import { useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import { deleteAssignment, restoreAssignment, type ClassroomAssignment } from "@/lib/api/classrooms";
import { removeAssignmentReference } from "@/lib/api/classroom-content";
import { useContentTranslation } from "./content-messages";
import { contentActionError } from "./content-action";

type Operation = "restore" | "remove" | "delete";
export function ArchivedAssignmentActions({ assignment, onChanged, disabled = false }: {
  assignment: ClassroomAssignment; onChanged: () => Promise<unknown>; disabled?: boolean;
}) {
  const { ct } = useContentTranslation();
  const [operation, setOperation] = useState<Operation | null>(null), [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null), [reload, setReload] = useState(false);
  const [expired, setExpired] = useState(false);
  const running = useRef(false);
  function prepare(next: Operation) {
    setExpired([assignment.due_at, assignment.cutoff_at].some(value => !!value && new Date(value).valueOf() < Date.now()));
    setError(null); setOperation(next);
  }
  async function run() {
    if (running.current || disabled) return;
    running.current = true; setPending(true); setError(null);
    let saved = false;
    try {
      if (!reload) {
        if (operation === "restore") await restoreAssignment(assignment.classroom_id, assignment.id);
        else if (operation === "delete") await deleteAssignment(assignment.classroom_id, assignment.id);
        else if (operation === "remove") await removeAssignmentReference(assignment.classroom_id, assignment.id);
        else return;
        saved = true; setReload(true);
      }
      await onChanged(); setReload(false); setOperation(null);
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "ASSIGNMENT_HISTORY_PROTECTED") {
        setError(ct("assignmentProtected")); setOperation(null);
      } else setError(saved || reload ? ct("refreshFailed") : contentActionError(caught, ct));
    } finally { running.current = false; setPending(false); }
  }
  const label = operation === "restore" ? ct("restore") : operation === "delete" ? ct("permanentDelete") : ct("remove");
  const title = operation === "restore" ? ct("restoreAssignmentTitle") : operation === "delete" ? ct("permanentDeleteTitle") : ct("removeAssignmentTitle");
  const description = operation === "restore" ? ct("restoreAssignmentDescription") + (expired ? " " + ct("restoreExpired") : "") : operation === "delete" ? ct("permanentDeleteDescription") : ct("removeAssignmentDescription");
  return <span className="classroom-action classroom-archive-actions">
    {reload ? <button type="button" disabled={pending} onClick={() => void run()}>{ct("retry")}</button> : <>
      <button type="button" disabled={disabled || pending} onClick={() => prepare("restore")}>{ct("restore")}</button>
      <button type="button" disabled={disabled || pending} onClick={() => prepare("remove")}>{ct("remove")}</button>
      <button type="button" disabled={disabled || pending} onClick={() => prepare("delete")}>{ct("permanentDelete")}</button>
    </>}
    {error && !operation ? <span role="alert" className="notice notice-error">{error}</span> : null}
    <ConfirmDialog open={operation !== null} title={title} description={description} confirmLabel={reload ? ct("retry") : label} pending={pending} errorMessage={error ?? undefined} onCancel={() => { if (!pending) setOperation(null); }} onConfirm={() => void run()} />
  </span>;
}
