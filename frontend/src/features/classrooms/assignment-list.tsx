"use client";
import { useState, type ReactNode } from "react";
import { AlertIcon, ArchiveIcon, LibraryIcon, SearchIcon } from "@/components/ui/icons";
import type { ClassroomAssignment } from "@/lib/api/classrooms";
import { normalizeClassworkSearch } from "./content/classwork-search";
import { useContentTranslation } from "./content/content-messages";
import { useAssignmentTargetLabel } from "./assignment-target";
import { AssignmentRow, type AssignmentRowPermissions } from "./assignments/assignment-row";
import { AssignmentCreationPanel } from "./assignments/creation-panel";
import { AssignmentSyncContext } from "./assignments/assignment-sync";
import { useAssignmentsText } from "./assignments/messages";
import "./assignments/assignments.css";

type Props = Partial<AssignmentRowPermissions> & { assignments: ClassroomAssignment[]; creationForm?: ReactNode; creationRequest?: number; selectedAssignmentId?: string | null; selectedAssignmentRequest?: number };
export function AssignmentList({ assignments, canViewResults = false, canStart = true, canSchedule = false, canArchive = false, archived = false, resultNamespace = "teacher", onChanged, creationForm, creationRequest, selectedAssignmentId, selectedAssignmentRequest }: Props) {
  const { at } = useAssignmentsText(), { ct } = useContentTranslation(), targetLabel = useAssignmentTargetLabel();
  const [status, setStatus] = useState("ALL"), [query, setQuery] = useState("");
  const words = normalizeClassworkSearch(query).split(/\s+/).filter(Boolean);
  const shown = assignments.filter(item => {
    if (status !== "ALL" && item.status !== status) return false;
    const text = normalizeClassworkSearch([item.title, item.version?.test_title, item.note, item.target ? targetLabel(item.target, item.version) : ""].filter(Boolean).join(" "));
    return words.every(word => text.includes(word));
  });
  const permissions = { canViewResults, canStart, canSchedule, canArchive, archived, resultNamespace, onChanged };
  const hasCreation = !!creationForm && canSchedule && !archived;
  return <section className="assignments-tab" aria-label={at("title")}>
    <header className="assignments-heading"><div className="assignments-heading-title"><span className="assignments-page-icon"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" /><path d="M14 3v6h6M8 13h8M8 17h6" /></svg></span><div><h2>{at("title")}</h2><p>{at("description")}</p></div></div>
      <div className="assignments-filters"><label className="assignments-search"><SearchIcon /><span className="sr-only">{at("search")}</span><input className="field" type="search" value={query} placeholder={at("placeholder")} onChange={event => setQuery(event.target.value)} />{query ? <button type="button" aria-label={at("clear")} onClick={() => setQuery("")}>×</button> : null}</label>
        <label><span className="sr-only">{at("filter")}</span><select className="select-field" value={status} onChange={event => setStatus(event.target.value)}><option value="ALL">{at("all")}</option><option value="ACTIVE">{at("active")}</option><option value="ARCHIVED">{at("archived")}</option></select></label>
      </div>
    </header>
    <div className="assignments-layout" data-creation={hasCreation}>
      {hasCreation ? <AssignmentSyncContext.Provider value={onChanged}><AssignmentCreationPanel request={creationRequest}>{creationForm}</AssignmentCreationPanel></AssignmentSyncContext.Provider> : null}
      <div className="assignments-sections">
        {(["ACTIVE", "ARCHIVED"] as const).map(kind => {
          const items = shown.filter(item => item.status === kind);
          if (!items.length) return null;
          const historical = kind === "ARCHIVED", Icon = historical ? ArchiveIcon : LibraryIcon;
          return <section key={kind} className={`assignments-group${historical ? " assignments-archive" : ""}`} aria-label={at(historical ? "archived" : "active")}>
            <header className="assignments-group-heading"><span className="assignments-group-icon"><Icon /></span><div><h3>{at(historical ? "archived" : "active")}</h3><p>{at(historical ? "archiveDescription" : "activeDescription")}</p></div><span className="assignments-count">{items.length} {at(items.length === 1 ? "countOne" : "count")}</span></header>
            <div className="assignments-rows">{items.map(assignment => <AssignmentRow key={assignment.id} assignment={assignment} focused={assignment.id === selectedAssignmentId} focusRequest={assignment.id === selectedAssignmentId ? selectedAssignmentRequest : 0} {...permissions} />)}</div>
            {historical ? <p className="assignments-archive-notice"><AlertIcon /><span>{ct("archiveNotice")}</span></p> : null}
          </section>;
        })}
        {!shown.length ? <p className="assignments-empty" role="status">{at(assignments.length ? "noMatches" : "empty")}</p> : null}
      </div>
    </div>
  </section>;
}
