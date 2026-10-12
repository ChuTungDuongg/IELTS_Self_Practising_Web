"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { startAssignment, archiveAssignment, type ClassroomAssignment, } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { ApiError } from "@/lib/api/client";
import { ResourceAction } from "./resource-action";
type ModuleType = "READING" | "LISTENING" | "WRITING" | "SPEAKING";
function StartAssignment({ assignment }: {
  assignment: ClassroomAssignment;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const available = assignment.version?.modules.map(item => item.module_type)
    ?? ["READING", "LISTENING", "WRITING"] as ModuleType[];
  const fullMockReady = ["LISTENING", "READING", "WRITING", "SPEAKING"].every(kind => assignment.version?.modules.some(item => item.module_type === kind && (item.recommended_duration_seconds ?? 0) > 0));
  const [mode, setMode] = useState<string>(available[0] ?? "READING");
  const [focusedId, setFocusedId] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const moduleRecord = assignment.version?.modules.find(item => item.module_type === mode);
  const units = mode === "READING" ? moduleRecord?.reading_passages
    : mode === "LISTENING" ? moduleRecord?.listening_sections : mode === "WRITING" ? moduleRecord?.writing_tasks : undefined;
  async function start() {
    if (pending)
      return;
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
      if (result.test_session_id)
        router.push(`/test-session/${result.test_session_id}`);
      else if (result.attempt_id)
        router.push(`/attempt/${result.attempt_id}`);
    }
    catch (caught) {
      setError(caught instanceof ApiError ? caught.message : t("governance.error"));
      setPending(false);
    }
  }
  return <div className="mt-3">
    <label className="field-label">
      {t("assignment.mode")}
      <select className="select-field" value={mode} onChange={event => {
        setMode(event.target.value);
        setFocusedId("");
      }}>
        {available.map(kind => <option key={kind} value={kind}>{t(moduleTranslationKeys[kind])}</option>)}
        {fullMockReady ? <option value="FULL_MOCK">{t("assignment.fullMock")}</option> : null}
      </select>
    </label>
    {mode !== "FULL_MOCK" && units?.length ? <label className="field-label mt-2">
      {t("assignment.module")}
      <select className="select-field" value={focusedId} onChange={event => setFocusedId(event.target.value)}>
        <option value="">{t("assignment.fullModule")}</option>
        {units.map(unit => <option key={unit.id} value={unit.id}>
          {t(mode === "WRITING" ? "common.taskNumber" : mode === "READING" ? "common.passageNumber" : "common.sectionNumber", { number: "task_number" in unit ? unit.task_number : unit.order_index + 1 })}
        </option>)}
      </select>
    </label> : null}
    <button className="btn btn-primary mt-2" disabled={pending || !available.length} onClick={() => void start()}>
      {t("assignment.start")}
    </button>
    {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
  </div>;
}
export function AssignmentList({ assignments, canManage = false, archived = false, resultNamespace = "teacher", }: {
  assignments: ClassroomAssignment[];
  canManage?: boolean;
  archived?: boolean;
  resultNamespace?: "teacher" | "shared";
}) {
  const { t } = useTranslation();
  return <section aria-label={t("assignment.title")}>
    <h2 className="section-title mb-3">{t("assignment.title")}</h2>
    {assignments.length ? <div className="test-card-grid">
      {assignments.map(assignment => <article key={assignment.id} className="surface-card p-5">
        <h3>{assignment.title ?? assignment.version?.test_title ?? t("assignment.title")}</h3>
        <p>{assignment.note}</p>
        {canManage ? <div className="flex gap-2 mt-3">
          <Link href={`${resultNamespace === "shared" ? "" : "/teacher"}/classrooms/${assignment.classroom_id}/assignments/${assignment.id}/results`} className="btn btn-secondary">
            {t("assignment.results")}
          </Link>
          {!archived && assignment.status === "ACTIVE" ? <ResourceAction action={() => archiveAssignment(assignment.classroom_id, assignment.id)}>
            {t("common.archive")}
          </ResourceAction> : null}
        </div> : !archived && assignment.status === "ACTIVE" ? <StartAssignment assignment={assignment} />
          : <p>{t("classroom.archived")}</p>}
      </article>)}
    </div> : <p>{t("assignment.empty")}</p>}
  </section>;
}
