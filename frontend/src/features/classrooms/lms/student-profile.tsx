"use client";
import { useCallback, useState } from "react";
import { getAcademicProfile } from "@/lib/api/classroom-lms";
import { GradeDetails } from "./gradebook";
import { useLmsText } from "./messages";
import { useScheduleText } from "../scheduling/messages";
import { LmsLoadState, useLmsData } from "./use-lms-data";

export function AcademicProfilePanel({ classroomId, studentId, onClose }: { classroomId: string; studentId: string; onClose: () => void }) {
  const { lt } = useLmsText(), { st } = useScheduleText(), [historyOffset, setHistoryOffset] = useState(0), [assignmentOffset, setAssignmentOffset] = useState(0);
  const load = useCallback((signal: AbortSignal) => getAcademicProfile(classroomId, studentId, { history_offset: historyOffset, assignment_offset: assignmentOffset }, signal), [classroomId, studentId, historyOffset, assignmentOffset]);
  const state = useLmsData(load), data = state.data;
  return <section className="lms-profile"><div className="classroom-section-heading"><h2>{lt("profile")}{data ? ` · ${data.display_name}` : ""}</h2><button type="button" className="btn btn-secondary" onClick={onClose}>{lt("close")}</button></div><LmsLoadState {...state} retry={state.refresh} />{data ? <><p>{lt(data.active_member ? "current" : "former")}</p><p className="classroom-meta">{lt("bounded")}</p><dl className="lms-metrics">{Object.entries(data.counts).map(([key, value]) => <div key={key}><dt>{st(key)}</dt><dd>{value}</dd></div>)}</dl><h3>{lt("assignments")}</h3><ul className="lms-record-list">{data.assignments.map(cell => <li key={cell.assignment_id}>{st(cell.submission_status)} · {cell.attempts_used} {st("attempts")}{cell.score ? <GradeDetails score={cell.score} classroomId={classroomId} /> : null}</li>)}</ul><div className="lms-pagination"><button disabled={!assignmentOffset} onClick={() => setAssignmentOffset(value => Math.max(0, value - 20))}>{lt("previous")}</button><button disabled={assignmentOffset + 20 >= data.total_assignments} onClick={() => setAssignmentOffset(value => value + 20)}>{lt("next")}</button></div><h3>{lt("history")}</h3><ul className="lms-record-list">{data.history.map(score => <li key={score.root_id}><GradeDetails score={score} classroomId={classroomId} /></li>)}</ul><div className="lms-pagination"><button disabled={!historyOffset} onClick={() => setHistoryOffset(value => Math.max(0, value - 50))}>{lt("previous")}</button><button disabled={historyOffset + 50 >= data.total_history} onClick={() => setHistoryOffset(value => value + 50)}>{lt("next")}</button></div></> : null}</section>;
}
