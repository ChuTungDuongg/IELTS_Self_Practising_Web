"use client";
import { useState } from "react";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { ScheduleEditor } from "./schedule-editor";
import { AssignmentMonitoringPanel } from "./assignment-monitoring";
import { useScheduleText } from "./messages";
import { AssignmentTargetSummary } from "../assignment-target";
export function AssignmentManagement({ assignment, canEdit, shared, canMonitor = true, initialEditing = false, onChanged }: { assignment: ClassroomAssignment; canEdit: boolean; shared: boolean; canMonitor?: boolean; initialEditing?: boolean; onChanged?: () => Promise<unknown> }) {
  const { st } = useScheduleText(), [open, setOpen] = useState(false), [editing, setEditing] = useState(initialEditing), [current, setCurrent] = useState(assignment), [syncError, setSyncError] = useState(false);
  return <div className="assignment-management">{canMonitor ? <button className="btn btn-secondary" type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{st(open ? "close" : "monitor")}</button> : null}{canEdit ? <button className="btn btn-secondary" type="button" onClick={() => setEditing(value => !value)}>{st("edit")}</button> : null}
    {editing && canEdit ? <ScheduleEditor assignment={current} onCancel={() => setEditing(false)} onSaved={value => { setCurrent(value); setEditing(false); if (onChanged) void onChanged().catch(() => setSyncError(true)); }} /> : null}
    {syncError ? <p role="alert">{st("error")}<button className="classroom-text-button" type="button" onClick={() => { if (onChanged) void onChanged().then(() => setSyncError(false)).catch(() => setSyncError(true)); }}>{st("retry")}</button></p> : null}
    {open && canMonitor ? <><AssignmentTargetSummary assignment={current} /><AssignmentMonitoringPanel classroomId={current.classroom_id} assignmentId={current.id} canEdit={canEdit} shared={shared} /></> : null}</div>;
}
