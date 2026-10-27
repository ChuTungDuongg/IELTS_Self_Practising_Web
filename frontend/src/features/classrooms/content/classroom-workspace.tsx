"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getClasswork, type Classwork } from "@/lib/api/classroom-content";
import type { Classroom, ClassroomAssignment } from "@/lib/api/classrooms";
import { AssignmentList } from "../assignment-list";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { ClassroomStream } from "./classroom-stream";
import { ClassworkPanel } from "./classwork-panel";
import { ordered } from "./classwork-order";
import "./classroom-workspace.css";
import "../scheduling/scheduling.css";
import { AssignmentProgressProvider } from "../scheduling/progress-provider";
import { AssignmentCalendarPanel } from "../scheduling/assignment-calendar";
import { useScheduleText } from "../scheduling/messages";

type Tab = "stream" | "classwork" | "assignments" | "calendar" | "people";
export function ClassroomWorkspace(props: Parameters<typeof ClassroomWorkspaceContent>[0]) {
  return <AssignmentProgressProvider classroomId={props.classroom.id} ids={props.assignments.map(item => item.id)} assignments={props.assignments} staff={props.canManage}><ClassroomWorkspaceContent {...props} /></AssignmentProgressProvider>;
}
function ClassroomWorkspaceContent({ classroom, user, assignments, people, assignmentForm, canManage, selectedPostId = null, selectedAssignmentId = null }: {
  classroom: Classroom; user: { id: string; role: string }; assignments: ClassroomAssignment[]; people?: ReactNode; assignmentForm?: ReactNode; canManage: boolean; selectedPostId?: string | null; selectedAssignmentId?: string | null;
}) {
  const { ct } = useContentTranslation();
  const { st } = useScheduleText();
  const [tab, setTab] = useState<Tab>(selectedAssignmentId ? "assignments" : "stream"), [data, setData] = useState<Classwork | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [assignmentFocus, setAssignmentFocus] = useState<string | null>(selectedAssignmentId);
  const canOwn = user.role === "TEACHER" && user.id === classroom.teacher_id, archived = classroom.status === "ARCHIVED", canAuthor = canOwn && !archived;
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
  function sectionNavigate(id: string) { setTab("classwork"); requestAnimationFrame(() => document.getElementById(`section-${id}`)?.scrollIntoView?.({ block: "start" })); }
  const tabs: Tab[] = ["stream", "classwork", "assignments", "calendar", "people"];
  return <div className="classroom-workspace" data-ui>
    {archived ? <p className="notice" role="status">{ct("archivedRoom")}</p> : user.role === "ADMIN" ? <p className="classroom-meta">{ct("readOnly")}</p> : null}
    <div className="classroom-tabs" role="tablist" aria-label={classroom.name} onKeyDown={event => {
      const index = tabs.indexOf(tab); const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); setTab(tabs[next]); document.getElementById(`classroom-tab-${tabs[next]}`)?.focus(); }
    }}>{tabs.map(key => <button key={key} id={`classroom-tab-${key}`} type="button" role="tab" aria-selected={tab === key} aria-controls={`classroom-panel-${key}`} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)}>{key === "calendar" ? st("calendar") : ct(key)}</button>)}</div>
    <div className="classroom-columns">
      <aside className="classroom-course-nav"><div className="classroom-course-links"><h2>{ct("course")}</h2><nav aria-label={ct("course")}>
        {data?.sections.length ? ordered(data.sections).map(section => <button type="button" key={section.id} onClick={() => sectionNavigate(section.id)}>{section.title}{section.status !== "PUBLISHED" ? <span className="classroom-meta">{ct(section.status === "DRAFT" ? "draft" : "archived")}</span> : null}</button>) : <p className="classroom-meta">{loading ? ct("loading") : ct("emptyWork")}</p>}
      </nav></div><label className="classroom-course-picker field-label">{ct("course")}<select className="select-field" value="" disabled={!data?.sections.length} onChange={event => { if (event.target.value) sectionNavigate(event.target.value); }}><option value="">{ct("course")}</option>{data ? ordered(data.sections).map(section => <option key={section.id} value={section.id}>{section.title}</option>) : null}</select></label></aside>
      <div className="classroom-main" id={`classroom-panel-${tab}`} role="tabpanel" aria-labelledby={`classroom-tab-${tab}`} tabIndex={0}>
        {tab === "stream" ? <ClassroomStream classroomId={classroom.id} resources={data?.resources ?? []} userId={user.id} canAuthor={canAuthor} canInspect={canOwn || user.role === "ADMIN"} archived={archived} admin={user.role === "ADMIN"} onOpenAssignment={openAssignment} selectedPostId={selectedPostId} /> : null}
        {tab === "classwork" ? <>{loading && !data ? <div className="classroom-panel classroom-skeleton" role="status"><h2>{ct("classwork")}</h2><p>{ct("loading")}</p><div /><div /></div> : null}{error ? <div className="classroom-panel"><p role="alert" className="notice notice-error">{error}</p><button type="button" className="btn btn-secondary" disabled={loading} onClick={() => void refresh().catch(() => {})}>{ct("retry")}</button></div> : null}{data ? <ClassworkPanel classroomId={classroom.id} data={data} assignments={assignments} canAuthor={canAuthor} onRefresh={refresh} onChange={setData} onOpenAssignment={openAssignment} /> : null}</> : null}
        {tab === "assignments" ? <div className="classroom-assignments">{assignmentForm}<AssignmentList assignments={assignments} canManage={canManage} canSchedule={canAuthor} archived={archived} resultNamespace={user.role === "ADMIN" ? "shared" : "teacher"} /></div> : null}
        {tab === "calendar" ? <AssignmentCalendarPanel classroomId={classroom.id} onOpenAssignment={openAssignment} /> : null}
        {tab === "people" ? <section aria-label={ct("people")}><h2 className="section-title mb-3">{ct("people")}</h2>{people ?? <p className="classroom-empty">{ct("emptyPeople")}</p>}</section> : null}
      </div>
      <aside className="classroom-info"><h2>{ct("information")}</h2><p>{classroom.description || ct("noDescription")}</p><dl><div><dt>{ct("resources")}</dt><dd>{data ? data.resources.filter(resource => resource.status === "PUBLISHED").length : "—"}</dd></div><div><dt>{ct("assignments")}</dt><dd>{assignments.filter(assignment => assignment.status === "ACTIVE").length}</dd></div></dl>{error && tab !== "classwork" ? <div><p role="alert" className="classroom-meta">{error}</p><button className="classroom-text-button" type="button" disabled={loading} onClick={() => void refresh().catch(() => {})}>{ct("retry")}</button></div> : null}</aside>
    </div>
  </div>;
}
