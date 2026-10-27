"use client";

import Link from "next/link";
import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { updateResource, type ClassworkItem, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ResourceViewer } from "./resource-viewer";
import { ActionMenu } from "../lms/action-menu";
import { useAssignmentProgress } from "../scheduling/progress-provider";
import { ClassworkAssignmentMeta } from "./classwork-assignment-meta";

export function ClassworkItemRow({ item, resource, assignment, classroomId, sections, canAuthor, pending, first, last, onEdit, onRefresh, onMove, onPlace, onStep, onDrag, onDrop, onOpenAssignment }: {
  item?: ClassworkItem; resource?: ClassroomResource; assignment?: ClassroomAssignment; classroomId: string; sections: ClassroomSection[]; canAuthor: boolean; pending: boolean; first: boolean; last: boolean;
  onEdit: (resource: ClassroomResource) => void; onRefresh: () => Promise<unknown>; onMove: (id: string, sectionId: string | null) => void; onPlace: (id: string, sectionId: string | null) => void; onStep: (id: string, delta: number) => void;
  onDrag: (id: string) => void; onDrop: (id: string) => void; onOpenAssignment: (id: string) => void;
}) {
  const { ct } = useContentTranslation(), progress = useAssignmentProgress();
  const title = resource?.title ?? assignment?.title ?? assignment?.version?.test_title ?? ct("assignmentActivity");
  const archived = resource?.status === "ARCHIVED" || assignment?.status === "ARCHIVED";
  const result = assignment && !progress?.staff ? progress?.items[assignment.id]?.result_attempt_id : null;
  const Icon = resource ? ReadingIcon : BuilderIcon;
  if (!resource && !assignment) return null;
  return <li id={"classwork-" + (assignment ? "assignment-" + assignment.id : "resource-" + resource!.id)} tabIndex={-1} className="classroom-classwork-row"
    onDragOver={event => { if (canAuthor && item && !archived) { event.preventDefault(); event.stopPropagation(); } }}
    onDrop={event => { if (canAuthor && item && !archived) { event.preventDefault(); event.stopPropagation(); onDrop(item.id); } }}>
    <div className="classroom-item-identity"><Icon className="classroom-item-icon" /><div><h4>{title}</h4>
      {assignment ? <ClassworkAssignmentMeta assignment={assignment} /> : resource ? <p className="classroom-meta">{ct(resource.kind === "TEXT" ? "text" : resource.kind === "LINK" ? "link" : "file")}{resource.status === "DRAFT" ? " · " + ct("draft") : ""}</p> : null}
    </div></div>
    {resource ? <ResourceViewer resource={resource} compact /> : assignment ? <div className="classroom-item-navigation">{result ? <Link className="classroom-text-button" href={"/review/" + result}>{ct("viewResults")}</Link> : null}<button className="classroom-text-button" type="button" onClick={() => onOpenAssignment(assignment.id)}>{ct("viewDetails")}</button></div> : null}
    {canAuthor ? <ActionMenu label={ct("itemActions")} iconOnly>
      {item && !archived ? <button className="classroom-drag-handle" type="button" draggable={!pending} disabled={pending} aria-label={ct("dragItem") + ": " + title} onDragStart={event => { event.stopPropagation(); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", item.id); onDrag(item.id); }}>⠿</button> : null}
      {resource && !archived ? <>
        <button type="button" disabled={pending} onClick={() => onEdit(resource)}>{ct("edit")}</button>
        <ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: resource.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={onRefresh}>{ct(resource.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction>
        <ContentAction disabled={pending} action={() => updateResource(classroomId, resource.id, { status: "ARCHIVED" })} onDone={onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
      </> : null}
      {item ? <div className="classroom-toolbar"><button type="button" className="classroom-order-button" disabled={pending || first} aria-label={ct("moveUp", { name: title })} onClick={() => onStep(item.id, -1)}>↑</button><button type="button" className="classroom-order-button" disabled={pending || last} aria-label={ct("moveDown", { name: title })} onClick={() => onStep(item.id, 1)}>↓</button></div> : null}
      {item || assignment && !archived ? <label className="classroom-move-label"><span className="sr-only">{ct("moveTo", { name: title })}</span><select className="select-field" value={item?.section_id ?? ""} disabled={pending} onChange={event => item ? onMove(item.id, event.target.value || null) : onPlace(assignment!.id, event.target.value || null)}><option value="">{ct("uncategorized")}</option>{sections.filter(section => section.status !== "ARCHIVED" || section.id === item?.section_id).map(section => <option key={section.id} value={section.id}>{section.title}</option>)}</select></label> : null}
      {assignment ? <button type="button" onClick={() => onOpenAssignment(assignment.id)}>{ct("viewDetails")}</button> : null}
    </ActionMenu> : null}
  </li>;
}
