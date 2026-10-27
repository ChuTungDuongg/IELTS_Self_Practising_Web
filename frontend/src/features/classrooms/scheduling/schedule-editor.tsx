"use client";
import { useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api/client";
import { serializeSchedule, updateAssignmentSchedule, type SchedulePolicy } from "@/lib/api/assignment-scheduling";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { ScheduleFields } from "./schedule-fields";
import { scheduleError, useScheduleText } from "./messages";
import { useAssignmentProgress } from "./progress-provider";

export function ScheduleEditor({ assignment, onSaved, onCancel }: { assignment: ClassroomAssignment; onSaved: (assignment: ClassroomAssignment) => void; onCancel: () => void }) {
  const { st } = useScheduleText(), router = useRouter(), progress = useAssignmentProgress();
  const [draft, setDraft] = useState<(SchedulePolicy & { reason?: string }) | null>(null), [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const running = useRef(false);
  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); const form = new FormData(event.currentTarget);
    try { setDraft({ ...serializeSchedule(form), reason: String(form.get("reason") ?? "") }); } catch { setError(st("invalid")); }
  }
  async function save() {
    if (!draft || running.current) return; running.current = true; setPending(true); setError(null);
    try { const saved = await updateAssignmentSchedule(assignment.classroom_id, assignment.id, { ...draft, expected_revision: assignment.policy_revision ?? 0 }); onSaved({ ...saved, version: assignment.version }); await progress?.refresh(); router.refresh(); setDraft(null); }
    catch (caught) { setError(scheduleError(caught, st)); if (caught instanceof ApiError && caught.code === "ASSIGNMENT_CHANGED") { setConflict(true); setDraft(null); } }
    finally { running.current = false; setPending(false); }
  }
  return <><form onSubmit={prepare} className="classroom-panel"><ScheduleFields value={assignment} /><label className="field-label">{st("reason")}<textarea className="field" name="reason" maxLength={2000} /></label><p>{st("warning")}</p><div className="classroom-toolbar"><button className="btn btn-primary" disabled={pending || conflict}>{st("save")}</button><button className="btn btn-secondary" type="button" disabled={pending} onClick={onCancel}>{st("cancel")}</button>{conflict ? <button className="btn btn-secondary" type="button" onClick={() => { router.refresh(); onCancel(); }}>{st("retry")}</button> : null}</div>{error && !draft ? <p role="alert">{error}</p> : null}</form>
    <ConfirmDialog open={draft !== null} title={st("confirm")} description={st("warning")} confirmLabel={st("save")} cancelLabel={st("cancel")} pendingLabel={st("loading")} pending={pending} errorMessage={error ?? undefined} onCancel={() => setDraft(null)} onConfirm={() => void save()} /></>;
}
