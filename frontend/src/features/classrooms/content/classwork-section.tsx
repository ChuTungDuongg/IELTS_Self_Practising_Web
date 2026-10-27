"use client";

import { updateSection, type Classwork, type ClassroomResource, type ClassroomSection } from "@/lib/api/classroom-content";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { useContentTranslation } from "./content-messages";
import { ContentAction } from "./content-action";
import { ClassworkItemRow } from "./classwork-item-row";
import { ActionMenu } from "../lms/action-menu";
import { useLmsText } from "../lms/messages";
import { ordered } from "./classwork-order";

export type ClassworkSectionActions = {
  onEditSection: (section: ClassroomSection) => void;
  onEditResource: (resource: ClassroomResource) => void;
  onAddResource: (sectionId: string | null) => void;
  onRefresh: () => Promise<unknown>;
  onSectionStep: (id: string, delta: number) => void;
  onSectionDrag: (id: string) => void;
  onSectionDrop: (id: string | null) => void;
  onDragEnd: () => void;
  onItemMove: (id: string, sectionId: string | null) => void;
  onItemStep: (id: string, delta: number) => void;
  onItemDrag: (id: string) => void;
  onItemDrop: (sectionId: string | null, beforeId?: string) => void;
  onOpenAssignment: (id: string) => void;
};
export function ClassworkSection({ section, index, sections, data, assignments, unplaced, classroomId, canAuthor, pending, actions }: {
  section: ClassroomSection | null; index: number; sections: ClassroomSection[]; data: Classwork; assignments: ClassroomAssignment[];
  unplaced: ClassroomAssignment[]; classroomId: string; canAuthor: boolean; pending: boolean; actions: ClassworkSectionActions;
}) {
  const { ct } = useContentTranslation(), { lt } = useLmsText();
  const id = section?.id ?? null, items = ordered(data.items.filter(item => item.section_id === id));
  return <section id={id ? `section-${id}` : "section-uncategorized"} className="classroom-panel classroom-course-section" aria-label={section?.title ?? ct("uncategorized")} aria-busy={pending}
    onDragOver={event => { if (canAuthor) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }}
    onDrop={event => { if (canAuthor) { event.preventDefault(); actions.onSectionDrop(id); } }} onDragEnd={actions.onDragEnd}>
    <header className="classroom-section-heading">
      <div><h3>{section?.title ?? ct("uncategorized")}</h3>{section && canAuthor ? <p className="classroom-meta">{ct(section.status === "DRAFT" ? "draft" : section.status === "PUBLISHED" ? "published" : "archived")}</p> : null}</div>
      {canAuthor && section ? <ActionMenu label={lt("topicActions")}>
        <button className="classroom-order-button" type="button" disabled={pending || index === 0} aria-label={ct("moveUp", { name: section.title })} onClick={() => actions.onSectionStep(section.id, -1)}>↑</button>
        <button className="classroom-order-button" type="button" disabled={pending || index === sections.length - 1} aria-label={ct("moveDown", { name: section.title })} onClick={() => actions.onSectionStep(section.id, 1)}>↓</button>
        <button className="classroom-drag-handle" type="button" disabled={pending} draggable={!pending} aria-label={`${ct("dragSection")}: ${section.title}`} onDragStart={event => { actions.onSectionDrag(section.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", section.id); }}>⠿</button>
      {section.status !== "ARCHIVED" ? <>
        <button className="classroom-text-button" type="button" disabled={pending} onClick={() => actions.onEditSection(section)}>{ct("edit")}</button>
        <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: section.status === "DRAFT" ? "PUBLISHED" : "DRAFT" })} onDone={actions.onRefresh}>{ct(section.status === "DRAFT" ? "publish" : "unpublish")}</ContentAction>
        <ContentAction disabled={pending} action={() => updateSection(classroomId, section.id, { status: "ARCHIVED" })} onDone={actions.onRefresh} confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }}>{ct("archive")}</ContentAction>
      <button className="classroom-text-button" type="button" disabled={pending} onClick={() => actions.onAddResource(id)}>{ct("addResource")}</button>
      </> : null}</ActionMenu> : null}
    </header>
    <details open className="classroom-topic-content"><summary>{lt("materials")} ({items.length + (!section ? unplaced.length : 0)})</summary>
    {section?.description ? <p>{section.description}</p> : null}
    <ul className="classroom-classwork-list">
      {items.map((item, itemIndex) => <ClassworkItemRow key={item.id} item={item}
        resource={data.resources.find(resource => resource.id === item.resource_id)} assignment={assignments.find(assignment => assignment.id === item.assignment_id)}
        classroomId={classroomId} sections={sections} canAuthor={canAuthor} pending={pending} first={itemIndex === 0} last={itemIndex === items.length - 1}
        onEdit={actions.onEditResource} onRefresh={actions.onRefresh} onMove={actions.onItemMove} onStep={actions.onItemStep} onDrag={actions.onItemDrag}
        onDrop={beforeId => actions.onItemDrop(id, beforeId)} onOpenAssignment={actions.onOpenAssignment} />)}
      {!section ? unplaced.map(assignment => <ClassworkItemRow key={assignment.id} assignment={assignment} classroomId={classroomId} sections={sections} canAuthor={false} pending={pending} first last
        onEdit={actions.onEditResource} onRefresh={actions.onRefresh} onMove={actions.onItemMove} onStep={actions.onItemStep} onDrag={actions.onItemDrag} onDrop={() => {}} onOpenAssignment={actions.onOpenAssignment} />) : null}
    </ul>
    {!items.length && (section || !unplaced.length) ? <p className="classroom-empty">{ct("emptySection")}</p> : null}
    </details>
  </section>;
}
