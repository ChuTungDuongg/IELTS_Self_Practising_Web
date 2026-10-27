"use client";
import { useRef, useState, type FormEvent } from "react";
import { localDateTime, saveExtension, revokeExtension, type AssignmentExtension, type ExtensionInput } from "@/lib/api/assignment-scheduling";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ContentAction } from "../content/content-action";
import { scheduleError, useScheduleText } from "./messages";
export function ExtensionEditor({ classroomId, assignmentId, studentId, name, value, onDone }: { classroomId: string; assignmentId: string; studentId: string; name: string; value: AssignmentExtension | null; onDone: () => Promise<void> }) {
  const { st } = useScheduleText(); const [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null); const running = useRef(false);
  const [overrideDue, setOverrideDue] = useState(Boolean(value?.override_due && !value.revoked)), [overrideCutoff, setOverrideCutoff] = useState(Boolean(value?.override_cutoff && !value.revoked));
  const [draft, setDraft] = useState<ExtensionInput | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (running.current) return; const form = new FormData(event.currentTarget);
    const instant = (key: string) => form.get(key) ? new Date(String(form.get(key))).toISOString() : null;
    setError(null);
    try { setDraft({ override_due: form.get("override_due") === "on", due_at_override: instant("due_at_override"), override_cutoff: form.get("override_cutoff") === "on", cutoff_at_override: instant("cutoff_at_override"), additional_attempts: Number(form.get("additional_attempts") ?? 0), reason: String(form.get("reason") ?? "") || null }); } catch { setError(st("invalid")); }
  }
  async function save() {
    if (!draft || running.current) return;
    running.current = true; setPending(true); setError(null);
    try { await saveExtension(classroomId, assignmentId, studentId, draft); await onDone(); setDraft(null); }
    catch (caught) { setError(scheduleError(caught, st)); }
    finally { running.current = false; setPending(false); }
  }
  return <section className="classroom-panel"><h4>{st("extensions")} · {name}</h4><form onSubmit={submit}><fieldset disabled={pending}>
    <p className="classroom-meta">{st("inherit")}</p>
    <label><input type="checkbox" name="override_due" checked={overrideDue} onChange={event => setOverrideDue(event.target.checked)} /> {st("overrideDue")}</label><label className="field-label">{st("due")}<input className="field" name="due_at_override" type="datetime-local" disabled={!overrideDue} defaultValue={localDateTime(value?.due_at_override)} /></label>
    <label><input type="checkbox" name="override_cutoff" checked={overrideCutoff} onChange={event => setOverrideCutoff(event.target.checked)} /> {st("overrideCutoff")}</label><label className="field-label">{st("cutoff")}<input className="field" name="cutoff_at_override" type="datetime-local" disabled={!overrideCutoff} defaultValue={localDateTime(value?.cutoff_at_override)} /></label>
    <label className="field-label">{st("extra")}<input className="field" type="number" name="additional_attempts" defaultValue={value?.additional_attempts ?? 0} min={0} max={10000} step={1} required /></label>
    <label className="field-label">{st("reason")}<textarea className="field" name="reason" maxLength={2000} defaultValue={value?.reason ?? ""} /></label><p>{st("warning")}</p><button className="btn btn-primary" disabled={pending}>{st("grant")}</button>
  </fieldset>{error ? <p role="alert">{error}</p> : null}</form>
    {value && !value.revoked ? <ContentAction disabled={pending} action={() => revokeExtension(classroomId, assignmentId, studentId)} onDone={onDone} confirm={{ title: st("revoke"), description: st("warning") }}>{st("revoke")}</ContentAction> : null}
    <ConfirmDialog open={draft !== null} title={st("grant")} description={st("warning")} confirmLabel={st("grant")} cancelLabel={st("cancel")} pendingLabel={st("loading")} pending={pending} errorMessage={error ?? undefined} onCancel={() => setDraft(null)} onConfirm={() => void save()} />
  </section>;
}
