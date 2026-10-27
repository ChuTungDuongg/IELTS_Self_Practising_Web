"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { startAssignment, type ClassroomAssignment } from "@/lib/api/classrooms";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { PresentationDialog } from "@/features/exam/presentation-dialog";
import { rememberAttemptPresentation, rememberSessionPresentation, type AttemptPresentationMode } from "@/features/exam/attempt-presentation";
import { useAssignmentProgress } from "../scheduling/progress-provider";
import { scheduleError, useScheduleText } from "../scheduling/messages";
type ModuleType = "READING" | "LISTENING" | "WRITING" | "SPEAKING";
export function StartAssignment({ assignment }: {
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
  const [selectedMode, setMode] = useState<string>(available[0] ?? "READING");
  const [selectedFocus, setFocusedId] = useState("");
  const mode = assignment.target ? assignment.target.mode === "FULL_MOCK" ? "FULL_MOCK" : assignment.target.module! : selectedMode;
  const focusedId = assignment.target ? assignment.target.focused_unit?.id ?? "" : selectedFocus;
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
      const target = assignment.target;
      const result = await startAssignment(assignment.id, target ? target.mode === "FULL_MOCK" ? { mode: "FULL_MOCK" } : { mode: "MODULE", module: target.module!, scope: target.scope ?? "FULL_MODULE", ...(target.focused_unit ? { focused_unit: target.focused_unit } : {}), ...(target.module === "SPEAKING" ? { speaking_mode: target.scope === "FOCUSED_UNIT" ? "PRACTICE" as const : "EXAM" as const } : {}), timer: { mode: "COUNT_UP" } } : mode === "FULL_MOCK"
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
    {!assignment.target ? <><label className="field-label">
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
    </label> : null}</> : null}
    <button ref={trigger} className="btn btn-primary mt-2" disabled={pending || !available.length || !allowed} onClick={() => { if (mode === "READING" || mode === "LISTENING" || mode === "FULL_MOCK") setChoosing(true); else void start(); }}>
      {t("assignment.start")}
    </button>
    {error && !choosing ? <p role="alert" className="notice notice-error">{error}</p> : null}
    {mode === "READING" || mode === "LISTENING" || mode === "FULL_MOCK" ? <PresentationDialog open={choosing} module={mode === "FULL_MOCK" ? "LISTENING" : mode} value={presentation} onChange={setPresentation} onClose={() => setChoosing(false)} onConfirm={() => void start()} pending={pending} error={error} returnFocusRef={trigger} preview={{ title: assignment.title ?? assignment.version?.test_title, unitTitle: previewUnit?.title, questionTypes: previewUnit?.question_groups.map(group => group.question_type) }} /> : null}
  </div>;
}
