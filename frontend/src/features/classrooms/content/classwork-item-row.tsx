"use client";

import { updateResource, type ClassworkItem, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ResourceViewer } from "./resource-viewer";
export function ClassworkItemRow({ item, resource, assignment, classroomId, sections, canAuthor, pending, first, last, onEdit, onRefresh, onMove, onStep, onDrag, onDrop, onOpenAssignment }: {
  item?: ClassworkItem; resource?: ClassroomResource; assignment?: ClassroomAssignment; classroomId: string; sections: ClassroomSection[]; canAuthor: boolean; pending: boolean; first: boolean; last: boolean;
  onEdit: (resource: ClassroomResource) => void; onRefresh: () => Promise<unknown>; onMove: (id: string, sectionId: string | null) => void; onStep: (id: string, delta: number) => void;
  onDrag: (id: string) => void; onDrop: (id: string) => void; onOpenAssignment: (id: string) => void;
}) {
  const { ct } = useContentTranslation();
  const title = resource?.title ?? assignment?.title ?? assignment?.version?.test_title ?? ct("assignmentActivity");
  const archived = resource?.status === "ARCHIVED" || assignment?.status === "ARCHIVED";
  if (!resource && !assignment) return null;
  return <li className="classroom-classwork-row" onDragOver={event => { if (canAuthor && item) { event.preventDefault(); event.stopPropagation(); } }} onDrop={event => { if (canAuthor && item) { event.preventDefault(); event.stopPropagation(); onDrop(item.id); } }}>
    <div className="classroom-row-heading"><div><h4>{title}</h4><p className="classroom-meta">{ct(resource ? resource.kind === "TEXT" ? "text" : resource.kind === "LINK" ? "link" : "file" : "assignmentActivity")}{resource && resource.status !== "PUBLISHED" ? ` · ${ct(resource.status === "DRAFT" ? "draft" : "archived")}` : assignment?.status === "ARCHIVED" ? ` · ${ct("archived")}` : ""}</p></div>
      {canAuthor && item ? <button className="classroom-drag-handle" type="button" draggable={!pending} disabled={pending} aria-label={`${ct("dragItem")}: ${title}`} onDragStart={event => { event.stopPropagation(); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.id); onDrag(item.id); }}>⠿</button> : null}
    </div>
    {resource ? <ResourceViewer resource={resource} /> : assignment ? <button className="classroom-text-button" type="button" onClick={() => onOpenAssignment(assignment.id)}>{ct("openAssignment")}</button> : null}
    {canAuthor ? <div className="classroom-item-controls">
      {resource && !archived ? <div className="classroom-toolbar"><button type="button" className="classroom-text-button" disabled={pending} onClick={() => onEdit(resource)}>{ct("edit")}</button><ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: resource.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={onRefresh}>{ct(resource.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction><ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: "ARCHIVED" })} onDone={onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction></div> : null}
      {item ? <div className="classroom-toolbar"><button type="button" className="classroom-order-button" disabled={pending || first} aria-label={ct("moveUp", { name: title })} onClick={() => onStep(item.id, -1)}>↑</button><button type="button" className="classroom-order-button" disabled={pending || last} aria-label={ct("moveDown", { name: title })} onClick={() => onStep(item.id, 1)}>↓</button><label className="classroom-move-label"><span className="sr-only">{ct("moveTo", { name: title })}</span><select className="select-field" value={item.section_id ?? ""} disabled={pending} onChange={event => onMove(item.id, event.target.value || null)}><option value="">{ct("uncategorized")}</option>{sections.filter(section => section.status !== "ARCHIVED" || section.id === item.section_id).map(section => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label></div> : null}
    </div> : null}
  </li>;
}
