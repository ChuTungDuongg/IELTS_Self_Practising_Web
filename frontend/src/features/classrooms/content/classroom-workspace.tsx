"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getClasswork, type Classwork } from "@/lib/api/classroom-content";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import { AssignmentList } from "../assignment-list";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { ClassroomStream } from "./classroom-stream";
import { ClassworkPanel } from "./classwork-panel";
import { ClassroomHeader } from "../lms/classroom-header";
import { GradebookPanel } from "../lms/gradebook";
import { useLmsText } from "../lms/messages";
import "./classroom-workspace.css";
import "../scheduling/scheduling.css";
import "../lms/lms.css";
import { AssignmentProgressProvider } from "../scheduling/progress-provider";
import { AssignmentCalendarPanel } from "../scheduling/assignment-calendar";
import { useScheduleText } from "../scheduling/messages";

type Tab = "stream" | "classwork" | "assignments" | "calendar" | "people" | "gradebook";
type WorkspaceProps = {
  classroom: Classroom; user: { id: string; role: string }; assignments: ClassroomAssignment[];
  people?: ReactNode; assignmentForm?: ReactNode; management?: ReactNode; canManage: boolean;
  selectedPostId?: string | null; selectedAssignmentId?: string | null;
};
export function ClassroomWorkspace(props: WorkspaceProps) {
  return <AssignmentProgressProvider classroomId={props.classroom.id} ids={props.assignments.map(item => item.id)} assignments={props.assignments} staff={props.canManage}><ClassroomWorkspaceContent {...props} /></AssignmentProgressProvider>;
}
function ClassroomWorkspaceContent({ classroom, user, assignments, people, assignmentForm, management, canManage, selectedPostId = null, selectedAssignmentId = null }: WorkspaceProps) {
  const { ct } = useContentTranslation(), { st } = useScheduleText(), { lt } = useLmsText();
  const [tab, setTab] = useState<Tab>(selectedAssignmentId ? "assignments" : "stream");
  const [data, setData] = useState<Classwork | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null);
  const [assignmentFocus, setAssignmentFocus] = useState<string | null>(selectedAssignmentId), [creating, setCreating] = useState(false);
  const canOwn = user.role === "TEACHER" && user.id === classroom.teacher_id, archived = classroom.status === "ARCHIVED";
  const canAuthor = (classroom.capabilities?.includes("content.manage") ?? canOwn) && !archived;
  const canSchedule = (classroom.capabilities?.includes("assignments.manage") ?? canOwn) && user.role !== "ADMIN";
  const requestId = useRef(0);
  const refresh = useCallback(async (signal?: AbortSignal) => {
    const sequence = ++requestId.current; setLoading(true); setError(null);
    try { const next = await getClasswork(classroom.id, undefined, signal); if (sequence === requestId.current && !signal?.aborted) setData(next); }
    catch (caught) { if (sequence === requestId.current && !signal?.aborted) setError(contentError(caught, ct("error"))); throw caught; }
    finally { if (sequence === requestId.current && !signal?.aborted) setLoading(false); }
  }, [classroom.id, ct]);
  useEffect(() => { const controller = new AbortController(); void Promise.resolve().then(() => { if (!controller.signal.aborted) void refresh(controller.signal).catch(() => {}); }); return () => controller.abort(); }, [refresh]);
  useEffect(() => {
    if (tab !== "assignments" || !assignmentFocus) return;
    const element = document.getElementById(`assignment-${assignmentFocus}`); element?.scrollIntoView?.({ block: "nearest" }); element?.focus();
  }, [tab, assignmentFocus]);
  function openAssignment(id: string) { setAssignmentFocus(id); setTab("assignments"); }
  const tabs: Tab[] = ["stream", "classwork", "assignments", "calendar", ...(canManage ? ["people" as const, "gradebook" as const] : [])];
  return <div className="classroom-workspace" data-ui>
    <ClassroomHeader classroom={classroom} management={management} onManage={canManage ? () => setTab("people") : undefined} canCreate={!!assignmentForm && !archived} onCreate={() => { setTab("assignments"); setCreating(true); }} />
    {archived ? <p className="notice" role="status">{ct("archivedRoom")}</p> : user.role === "ADMIN" ? <p className="classroom-meta">{ct("readOnly")}</p> : null}
    <div className="classroom-tabs" role="tablist" aria-label={classroom.name} onKeyDown={event => {
      const index = tabs.indexOf(tab); const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); setTab(tabs[next]); document.getElementById(`classroom-tab-${tabs[next]}`)?.focus(); }
    }}>{tabs.map(key => <button key={key} id={`classroom-tab-${key}`} type="button" role="tab" aria-selected={tab === key} aria-controls={`classroom-panel-${key}`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)}>{key === "gradebook" ? lt("gradebook") : key === "calendar" ? st("calendar") : ct(key)}</button>)}</div>
    <div className="classroom-columns">
      <div className="classroom-main" id={`classroom-panel-${tab}`} role="tabpanel" aria-labelledby={`classroom-tab-${tab}`} tabIndex={0}>
        {tab === "stream" && canManage ? <section className="classroom-overview" aria-label={lt("overview")}><div><strong>{assignments.filter(item => item.status === "ACTIVE").length}</strong><span>{lt("activeAssignments")}</span></div><div><strong>{classroom.active_member_count ?? "—"}</strong><span>{lt("students")}</span></div><div className="classroom-toolbar">{canAuthor ? <button type="button" className="btn btn-secondary" onClick={() => setTab("classwork")}>{lt("materials")}</button> : null}{people ? <button type="button" className="btn btn-secondary" onClick={() => setTab("people")}>{ct("people")}</button> : null}<button type="button" className="btn btn-secondary" onClick={() => setTab("gradebook")}>{lt("gradebook")}</button></div></section> : null}
        {tab === "stream" ? <ClassroomStream classroomId={classroom.id} resources={data?.resources ?? []} userId={user.id} canAuthor={canAuthor} canInspect={canManage} archived={archived} admin={user.role === "ADMIN"} onOpenAssignment={openAssignment} selectedPostId={selectedPostId} /> : null}
        {tab === "classwork" ? <>{loading && !data ? <div className="classroom-panel classroom-skeleton" role="status"><h2>{ct("classwork")}</h2><p>{ct("loading")}</p><div /><div /></div> : null}{error ? <div className="classroom-panel"><p role="alert" className="notice notice-error">{error}</p><button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void refresh().catch(() => {})}>{ct("retry")}</button></div> : null}{data ? <ClassworkPanel classroomId={classroom.id} data={data} assignments={assignments} canAuthor={canAuthor} onRefresh={refresh} onChange={setData} onOpenAssignment={openAssignment} /> : null}</> : null}
        {tab === "assignments" ? <div className="classroom-assignments">{assignmentForm && !archived ? <section className="classroom-create-assignment"><button type="button" className="btn btn-primary" aria-expanded={creating} onClick={() => setCreating(value => !value)}>{creating ? lt("close") : lt("newAssignment")}</button>{creating ? <div className="classroom-focused-form">{assignmentForm}</div> : null}</section> : null}<AssignmentList assignments={assignments} canManage={canManage} canSchedule={canSchedule} canArchive={canSchedule || user.role === "ADMIN"} archived={archived} resultNamespace={user.role === "TEACHER" ? "teacher" : "shared"} /></div> : null}
        {tab === "calendar" ? <AssignmentCalendarPanel classroomId={classroom.id} onOpenAssignment={openAssignment} /> : null}
        {tab === "people" && canManage ? <section aria-label={ct("people")}><h2 className="section-title mb-3">{ct("people")}</h2>{people ?? <p className="classroom-empty">{ct("emptyPeople")}</p>}</section> : null}
        {tab === "gradebook" && canManage ? <GradebookPanel classroomId={classroom.id} assignments={assignments} canEdit={!archived && canSchedule} /> : null}
      </div>
    </div>
  </div>;
}
