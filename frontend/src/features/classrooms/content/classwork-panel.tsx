"use client";

import { useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { placeAssignment, reorderItems, reorderSections, type Classwork, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useContentTranslation } from "./content-messages";
import { contentError } from "./content-action";
import { ordered, moveBy, targetItemOrder } from "./classwork-order";
import { ClassworkSection, type ClassworkSectionActions } from "./classwork-section";
import { SectionEditor } from "./section-editor";
import { ResourceEditor } from "./resource-editor";
import { useLmsText } from "../lms/messages";
import { ActionMenu } from "../lms/action-menu";

type Editor = { kind: "section"; section?: ClassroomSection } | { kind: "resource"; resource?: ClassroomResource; sectionId?: string | null } | { kind: "placement" };
export function ClassworkPanel({ classroomId, data, assignments, canAuthor, onRefresh, onChange, onOpenAssignment, initialAction, onCreateAssignment }: {
  classroomId: string; data: Classwork; assignments: ClassroomAssignment[]; canAuthor: boolean; onRefresh: () => Promise<unknown>; onChange: (data: Classwork) => void; onOpenAssignment: (id: string) => void;
  initialAction?: "section" | "resource"; onCreateAssignment?: () => void;
}) {
  const { ct } = useContentTranslation();
  const { lt } = useLmsText();
  const [editor, setEditor] = useState<Editor | null>(initialAction ? { kind: initialAction } : null), [pending, setPending] = useState(false), [error, setError] = useState<string | null>(null), [notice, setNotice] = useState<string | null>(null);
  const [assignmentId, setAssignmentId] = useState(""), [targetSection, setTargetSection] = useState("");
  const running = useRef(false), dragging = useRef<{ kind: "section" | "item"; id: string } | null>(null);
  const sections = ordered(data.sections), unplaced = assignments.filter(assignment => !data.items.some(item => item.assignment_id === assignment.id));
  async function mutate(action: () => Promise<Classwork>) {
    if (running.current || !canAuthor) return; running.current = true; setPending(true); setError(null); setNotice(null);
    try { onChange(await action()); setNotice(ct("reorderSaved")); }
    catch (caught) {
      if (caught instanceof ApiError && caught.code === "CLASSWORK_CHANGED") { try { await onRefresh(); setError(ct("conflict")); } catch (refreshError) { setError(contentError(refreshError, ct("error"))); } }
      else setError(contentError(caught, ct("error")));
    } finally { running.current = false; setPending(false); dragging.current = null; }
  }
  function sectionStep(id: string, delta: number) { void mutate(() => reorderSections(classroomId, moveBy(sections.map(section => section.id), id, delta), data.revision)); }
  function moveItem(id: string, sectionId: string | null, beforeId?: string) { void mutate(() => reorderItems(classroomId, sectionId, targetItemOrder(data.items, sectionId, id, beforeId), data.revision)); }
  function stepItem(id: string, delta: number) {
    const item = data.items.find(item => item.id === id); if (!item) return;
    void mutate(() => reorderItems(classroomId, item.section_id, moveBy(ordered(data.items.filter(row => row.section_id === item.section_id)).map(row => row.id), id, delta), data.revision));
  }
  function dropSection(id: string) {
    const drag = dragging.current; if (!drag || drag.kind !== "section" || drag.id === id) return;
    const ids = sections.filter(section => section.id !== drag.id).map(section => section.id); const index = ids.indexOf(id); ids.splice(index, 0, drag.id);
    void mutate(() => reorderSections(classroomId, ids, data.revision));
  }
  function dropItem(sectionId: string | null, beforeId?: string) { const drag = dragging.current; if (drag?.kind === "item" && drag.id !== beforeId) moveItem(drag.id, sectionId, beforeId); }
  async function editorDone() { await onRefresh(); setEditor(null); setNotice(ct("saved")); }
  const actions: ClassworkSectionActions = {
    onEditSection: section => setEditor({ kind: "section", section }), onEditResource: resource => setEditor({ kind: "resource", resource }),
    onAddResource: sectionId => setEditor({ kind: "resource", sectionId }), onRefresh, onSectionStep: sectionStep,
    onSectionDrag: id => { dragging.current = { kind: "section", id }; },
    onSectionDrop: id => { if (dragging.current?.kind === "section" && id) dropSection(id); else dropItem(id); },
    onDragEnd: () => { dragging.current = null; }, onItemMove: moveItem, onItemStep: stepItem,
    onItemDrag: id => { dragging.current = { kind: "item", id }; }, onItemDrop: dropItem, onOpenAssignment,
  };
  const sectionProps = { sections, data, assignments, unplaced, classroomId, canAuthor, pending, actions };
  return <section className="classroom-classwork" aria-label={ct("classwork")}>
    <div className="classroom-section-heading"><div><h2>{ct("classwork")}</h2><p className="classroom-meta">{lt("organizeTopics")}</p></div>{canAuthor ? <ActionMenu label={lt("addContent")} primary><button type="button" disabled={pending} onClick={() => setEditor({ kind: "section" })}>{ct("addSection")}</button><button type="button" disabled={pending} onClick={() => setEditor({ kind: "resource" })}>{ct("addResource")}</button><button type="button" disabled={pending} onClick={() => setEditor({ kind: "placement" })}>{ct("attachAssignment")}</button></ActionMenu> : null}</div>
    {error ? <p className="notice notice-error" role="alert">{error}</p> : null}{notice ? <p className="classroom-meta" role="status">{notice}</p> : null}
    {editor && canAuthor ? editor.kind === "section" ? <SectionEditor key={editor.section?.id ?? "new-section"} classroomId={classroomId} section={editor.section} onDone={editorDone} onCancel={() => setEditor(null)} /> : editor.kind === "resource" ? <ResourceEditor key={editor.resource?.id ?? `new-resource-${editor.sectionId ?? ""}`} classroomId={classroomId} resource={editor.resource} sectionId={editor.sectionId} sections={sections} onDone={editorDone} onCancel={() => setEditor(null)} /> : null : null}
    {canAuthor && editor?.kind === "placement" ? <div className="classroom-focused-form">{unplaced.some(assignment => assignment.status === "ACTIVE") ? <form className="classroom-panel classroom-association" onSubmit={event => { event.preventDefault(); if (assignmentId) void mutate(async () => { const next = await placeAssignment(classroomId, targetSection || null, assignmentId); setAssignmentId(""); setEditor(null); return next; }); }}>
      <h3>{ct("attachAssignment")}</h3><label className="field-label">{ct("chooseAssignment")}<select className="select-field" value={assignmentId} required disabled={pending} onChange={event => setAssignmentId(event.target.value)}><option value="">—</option>{unplaced.filter(assignment => assignment.status === "ACTIVE").map(assignment => <option key={assignment.id} value={assignment.id}>{assignment.title ?? assignment.version?.test_title ?? ct("assignmentActivity")}</option>)}</select></label><label className="field-label">{ct("section")}<select className="select-field" value={targetSection} disabled={pending} onChange={event => setTargetSection(event.target.value)}><option value="">{ct("uncategorized")}</option>{sections.filter(section => section.status !== "ARCHIVED").map(section => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label><button className="btn btn-secondary" disabled={pending || !assignmentId}>{ct("attachAssignment")}</button>
      <button type="button" className="btn btn-secondary" disabled={pending} onClick={() => setEditor(null)}>{ct("cancel")}</button>
    </form> : <div className="classroom-empty"><p>{lt("noEligibleAssignments")}</p>{onCreateAssignment ? <button type="button" className="btn btn-primary" onClick={onCreateAssignment}>{lt("newAssignment")}</button> : null}<button type="button" className="btn btn-secondary" onClick={() => setEditor(null)}>{ct("cancel")}</button></div>}{!sections.length ? <button type="button" className="classroom-text-button" onClick={() => setEditor({ kind: "section" })}>{ct("addSection")}</button> : null}</div> : null}
    {!sections.length ? <div className="classroom-empty"><p>{lt("emptySections")}</p>{canAuthor && !editor ? <button type="button" className="btn btn-primary" onClick={() => setEditor({ kind: "section" })}>{lt("newSection")}</button> : null}</div> : null}{sections.map((section, index) => <ClassworkSection key={section.id} section={section} index={index} {...sectionProps} />)}
    {data.items.some(item => item.section_id === null) || unplaced.length ? <ClassworkSection section={null} index={sections.length} {...sectionProps} /> : null}
  </section>;
}
