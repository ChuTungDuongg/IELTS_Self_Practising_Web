"use client";
import { useState } from "react";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { ScheduleEditor } from "./schedule-editor";
import { AssignmentMonitoringPanel } from "./assignment-monitoring";
import { useScheduleText } from "./messages";
export function AssignmentManagement({ assignment, canEdit, shared }: { assignment: ClassroomAssignment; canEdit: boolean; shared: boolean }) {
  const { st } = useScheduleText(), [open, setOpen] = useState(false), [editing, setEditing] = useState(false), [current, setCurrent] = useState(assignment);
  return <div className="assignment-management"><button className="btn btn-secondary" type="button" aria-expanded={open} onClick={() => setOpen(value => !value)}>{st(open ? "close" : "monitor")}</button>{canEdit ? <button className="btn btn-secondary" type="button" onClick={() => setEditing(value => !value)}>{st("edit")}</button> : null}
    {editing && canEdit ? <ScheduleEditor assignment={current} onCancel={() => setEditing(false)} onSaved={value => { setCurrent(value); setEditing(false); }} /> : null}
    {open ? <AssignmentMonitoringPanel classroomId={current.classroom_id} assignmentId={current.id} canEdit={canEdit} shared={shared} /> : null}</div>;
}
