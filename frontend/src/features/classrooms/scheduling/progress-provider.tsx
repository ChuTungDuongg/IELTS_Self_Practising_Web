"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getAssignmentProgress, type AssignmentProgress } from "@/lib/api/assignment-scheduling";
import { useScheduleText } from "./messages";
import type { ClassroomAssignment } from "@/lib/api/classrooms";

type ProgressState = { items: Record<string, AssignmentProgress>; loading: boolean; error: boolean; refresh: () => Promise<void>; staff: boolean; assignments: ClassroomAssignment[] };
const ProgressContext = createContext<ProgressState | null>(null);
const noAssignments: ClassroomAssignment[] = [];
export function useAssignmentProgress() { return useContext(ProgressContext); }
export function AssignmentProgressProvider({ classroomId, ids, children, staff = false, assignments = noAssignments }: { classroomId: string; ids: string[]; children: ReactNode; staff?: boolean; assignments?: ClassroomAssignment[] }) {
  const [items, setItems] = useState<Record<string, AssignmentProgress>>({}), [loading, setLoading] = useState(true), [error, setError] = useState(false);
  const signature = [...new Set(ids)].sort().join(","), sequence = useRef(0);
  const load = useCallback(async (signal?: AbortSignal) => {
    const current = ++sequence.current; setLoading(true); setError(false);
    try {
      const requested = signature && !staff ? signature.split(",") : [], next: Record<string, AssignmentProgress> = {};
      for (let start = 0; start < requested.length; start += 100) {
        const page = await getAssignmentProgress(classroomId, { assignmentIds: requested.slice(start, start+100) }, signal);
        page.items.forEach(item => { next[item.assignment_id] = item; });
      }
      if (sequence.current === current && !signal?.aborted) setItems(next);
    } catch { if (!signal?.aborted && sequence.current === current) setError(true); }
    finally { if (!signal?.aborted && sequence.current === current) setLoading(false); }
  }, [classroomId, signature, staff]);
  useEffect(() => { const controller = new AbortController(); void Promise.resolve().then(() => { if (!controller.signal.aborted) void load(controller.signal); }); return () => controller.abort(); }, [load]);
  const value = useMemo(() => ({ items, loading, error, refresh: load, staff, assignments }), [items, loading, error, load, staff, assignments]);
  return <ProgressContext.Provider value={value}>{children}</ProgressContext.Provider>;
}
export function ProgressLoadState() {
  const state = useAssignmentProgress(), { st } = useScheduleText();
  return state?.loading ? <p role="status">{st("loading")}</p> : state?.error ? <div><p role="alert">{st("error")}</p><button className="btn btn-secondary" type="button" onClick={() => void state.refresh()}>{st("retry")}</button></div> : null;
}
