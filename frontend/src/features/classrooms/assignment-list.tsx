"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { startAssignment, archiveAssignment, type ClassroomAssignment, } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { useContentTranslation } from "./content/content-messages";
import { ResourceAction } from "./resource-action";
import { PresentationDialog } from "@/features/exam/presentation-dialog";
import { rememberAttemptPresentation, rememberSessionPresentation, type AttemptPresentationMode } from "@/features/exam/attempt-presentation";
import { useAssignmentProgress } from "./scheduling/progress-provider";
import { ProgressSummary, ScheduleSummary } from "./scheduling/progress-summary";
import { AssignmentManagement } from "./scheduling/assignment-management";
import { scheduleError, useScheduleText } from "./scheduling/messages";
import { useLmsText } from "./lms/messages";
type ModuleType = "READING" | "LISTENING" | "WRITING" | "SPEAKING";
function StartAssignment({ assignment }: {
  assignment: ClassroomAssignment;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { st } = useScheduleText();
  const progressState = useAssignmentProgress();
  const allowed = !progressState || (!progressState.loading && !progressState.error && progressState.items[assignment.id]?.can_start === true);
  const available = assignment.version?.modules.map(item => item.module_type)
    ?? ["READING", "LISTENING", "WRITING"] as ModuleType[];
  const fullMockReady = ["LISTENING", "READING", "WRITING", "SPEAKING"].every(kind => assignment.version?.modules.some(item => item.module_type === kind && (item.recommended_duration_seconds ?? 0) > 0));
  const [mode, setMode] = useState<string>(available[0] ?? "READING");
  const [focusedId, setFocusedId] = useState("");
  const [pending, setPending] = useState(false);
  const [presentation, setPresentation] = useState<AttemptPresentationMode>("PRACTICE");
  const [choosing, setChoosing] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const starting = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const moduleRecord = assignment.version?.modules.find(item => item.module_type === mode);
  const units = mode === "READING" ? moduleRecord?.reading_passages
    : mode === "LISTENING" ? moduleRecord?.listening_sections : mode === "WRITING" ? moduleRecord?.writing_tasks : undefined;
  const previewModule = mode === "FULL_MOCK" ? assignment.version?.modules.find(item => item.module_type === "LISTENING") : moduleRecord;
  const previewUnits = mode === "READING" ? previewModule?.reading_passages : previewModule?.listening_sections;
  const previewUnit = previewUnits?.find(unit => unit.id === focusedId) ?? previewUnits?.[0];
  async function start() {
    if (starting.current || !allowed)
      return;
    starting.current = true;
    setPending(true);
    setError(null);
    try {
      const result = await startAssignment(assignment.id, mode === "FULL_MOCK"
        ? { mode: "FULL_MOCK" }
        : {
          mode: "MODULE",
          module: mode as ModuleType,
          ...(mode === "SPEAKING" ? { speaking_mode: "EXAM" as const } : {}),
          scope: focusedId ? "FOCUSED_UNIT" : "FULL_MODULE",
          ...(focusedId ? {
            focused_unit: {
              kind: mode === "READING" ? "READING_PASSAGE"
                : mode === "LISTENING" ? "LISTENING_PART" : "WRITING_TASK",
              id: focusedId,
            } as const,
          } : {}),
          timer: { mode: "COUNT_UP" },
        });
      await progressState?.refresh();
      if (result.test_session_id) {
        if (mode === "FULL_MOCK") rememberSessionPresentation(result.test_session_id, presentation);
        router.push(`/test-session/${result.test_session_id}`);
      }
      else if (result.attempt_id) {
        if (mode === "READING" || mode === "LISTENING") rememberAttemptPresentation({ attempt_id: result.attempt_id, module: mode, attempt_context: "STANDALONE", test_session_id: null }, presentation);
        router.push(`/attempt/${result.attempt_id}`);
      }
      setChoosing(false);
    }
    catch (caught) {
      await progressState?.refresh();
      setError(scheduleError(caught, st));
      setPending(false);
      starting.current = false;
    }
  }
  return <div className="mt-3">
    <label className="field-label">
      {t("assignment.mode")}
      <select className="select-field" value={mode} disabled={pending} onChange={event => {
        setMode(event.target.value);
        setFocusedId("");
      }}>
        {available.map(kind => <option key={kind} value={kind}>{t(moduleTranslationKeys[kind])}</option>)}
        {fullMockReady ? <option value="FULL_MOCK">{t("assignment.fullMock")}</option> : null}
      </select>
    </label>
    {mode !== "FULL_MOCK" && units?.length ? <label className="field-label mt-2">
      {t("assignment.module")}
      <select className="select-field" value={focusedId} disabled={pending} onChange={event => setFocusedId(event.target.value)}>
        <option value="">{t("assignment.fullModule")}</option>
        {units.map(unit => <option key={unit.id} value={unit.id}>
          {t(mode === "WRITING" ? "common.taskNumber" : mode === "READING" ? "common.passageNumber" : "common.sectionNumber", { number: "task_number" in unit ? unit.task_number : unit.order_index + 1 })}
        </option>)}
      </select>
    </label> : null}
    <button ref={trigger} className="btn btn-primary mt-2" disabled={pending || !available.length || !allowed} onClick={() => { if (mode === "READING" || mode === "LISTENING" || mode === "FULL_MOCK") setChoosing(true); else void start(); }}>
      {t("assignment.start")}
    </button>
    {error && !choosing ? <p role="alert" className="notice notice-error">{error}</p> : null}
    {mode === "READING" || mode === "LISTENING" || mode === "FULL_MOCK" ? <PresentationDialog open={choosing} module={mode === "FULL_MOCK" ? "LISTENING" : mode} value={presentation} onChange={setPresentation} onClose={() => setChoosing(false)} onConfirm={() => void start()} pending={pending} error={error} returnFocusRef={trigger} preview={{ title: assignment.title ?? assignment.version?.test_title, unitTitle: previewUnit?.title, questionTypes: previewUnit?.question_groups.map(group => group.question_type) }} /> : null}
  </div>;
}
export function AssignmentList({ assignments, canManage = false, canSchedule = canManage, canArchive = canManage, archived = false, resultNamespace = "teacher", }: {
  assignments: ClassroomAssignment[];
  canManage?: boolean;
  canSchedule?: boolean;
  canArchive?: boolean;
  archived?: boolean;
  resultNamespace?: "teacher" | "shared";
}) {
  const { t } = useTranslation();
  const { ct } = useContentTranslation();
  const { lt } = useLmsText(), [status, setStatus] = useState("ALL");
  const shown = assignments.filter(item => status === "ALL" || item.status === status);
  return <section aria-label={t("assignment.title")}>
    <div className="classroom-section-heading"><h2 className="section-title mb-3">{t("assignment.title")}</h2><label className="classroom-filter"><span className="sr-only">{lt("status")}</span><select className="select-field" value={status} onChange={event => setStatus(event.target.value)}><option value="ALL">{lt("all")}</option><option value="ACTIVE">{lt("active")}</option><option value="ARCHIVED">{lt("archive")}</option></select></label></div>
    {shown.length ? <div className="classroom-assignment-list">
      {shown.map(assignment => <article key={assignment.id} id={`assignment-${assignment.id}`} tabIndex={-1} className="classroom-panel classroom-assignment-row">
        <h3>{assignment.title ?? assignment.version?.test_title ?? t("assignment.title")}</h3>
        <p>{assignment.note}</p>
        {canManage ? <ScheduleSummary assignment={assignment} /> : <ProgressSummary assignmentId={assignment.id} actions />}
        {canManage ? <div className="flex gap-2 mt-3">
          <Link href={`${resultNamespace === "shared" ? "" : "/teacher"}/classrooms/${assignment.classroom_id}/assignments/${assignment.id}/results`} className="btn btn-secondary">
            {t("assignment.results")}
          </Link>
          {canArchive && !archived && assignment.status === "ACTIVE" ? <details><summary>{lt("more")}</summary><ResourceAction confirm={{ title: ct("archiveTitle"), description: ct("archiveDescription") }} action={() => archiveAssignment(assignment.classroom_id, assignment.id)}>
            {t("common.archive")}
          </ResourceAction></details> : null}
        </div> : !archived && assignment.status === "ACTIVE" ? <StartAssignment assignment={assignment} />
          : <p>{t("classroom.archived")}</p>}
        {canManage ? <AssignmentManagement key={`${assignment.id}-${assignment.policy_revision}`} assignment={assignment} canEdit={canSchedule && !archived && assignment.status === "ACTIVE"} shared={resultNamespace === "shared"} /> : null}
      </article>)}
    </div> : <p>{t("assignment.empty")}</p>}
  </section>;
}
