"use client";

import { moduleTranslationKeys } from "@/lib/i18n/translations";
import type { TranslationFunction } from "@/lib/i18n/types";
import { useTranslation } from "@/lib/i18n/locale-provider";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { formatDuration } from "@/features/exam/timer";
import { resumeAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { ExamPayload } from "@/lib/api/exam";
import { useExamDraftAutosave } from "./use-exam-draft-autosave";
import { DraftRecoveryNotices } from "./draft-recovery-notices";
import { questionSpan } from "@/features/questions/numbering";
import { focusedUnitLabel } from "./focused-attempt";

const pausedSave = async (): Promise<never> => { throw new Error("Resume before saving responses."); };

export function PausedAttemptGate({ exam }: { exam: ExamPayload }) {
  const { t } = useTranslation();
  const { attempt, test_title: testTitle } = exam;
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | { message: import("@/lib/i18n/types").TranslationKey }>();
  const responseLabels = (() => {
    const labels = new Map<string, string>();
    for (const task of exam.writing_tasks ?? []) labels.set(task.id, t("common.taskNumber", { number: task.task_number }));
    for (const passage of exam.passages ?? []) for (const group of passage.question_groups) for (const question of group.questions) labels.set(question.id, questionLabel(group.question_type, question.number, question.config, t));
    for (const part of exam.listening_parts ?? []) for (const group of part.question_groups) for (const question of group.questions) labels.set(question.id, questionLabel(group.question_type, question.number, question.config, t));
    return labels;
  })();
  const initialResponses = useMemo(() => [
    ...(exam.writing_tasks ?? []).map((task) => ({ id: task.id, value: task.content as unknown, revision: task.response_revision })),
    ...(exam.passages ?? []).flatMap((passage) => passage.question_groups.flatMap((group) => group.questions.map((question) => ({ id: question.id, value: question.value as unknown, revision: question.answer_revision })))),
    ...(exam.listening_parts ?? []).flatMap((part) => part.question_groups.flatMap((group) => group.questions.map((question) => ({ id: question.id, value: question.value as unknown, revision: question.answer_revision })))),
  ], [exam]);
  const { values, conflicts, recoveredIds, resolveConflict } = useExamDraftAutosave<unknown>({
    attempt, initialResponses, save: pausedSave, debounceMs: 400,
  });

  async function resume() {
    if (pending) return;
    setPending(true);
    setError(undefined);
    try {
      await resumeAttempt(attempt.attempt_id);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "runner.resumeError" });
      setPending(false);
    }
  }

  const frozenTime = attempt.timer_mode === "COUNTDOWN"
    ? t("runner.remaining", { time: formatDuration(attempt.remaining_seconds ?? 0) })
    : t("runner.practiceTime", { time: formatDuration(attempt.elapsed_seconds) });

  return <main className="paused-attempt-gate">
    <p className="page-eyebrow">{attempt.scope === "FOCUSED_UNIT" ? `${t(moduleTranslationKeys[attempt.module])} · ${focusedUnitLabel({ ...attempt, focused_unit: attempt.focused_unit ? { ...attempt.focused_unit, title: null } : null }, t) ?? t("runner.focused")}` : `${t(moduleTranslationKeys[attempt.module])} · ${t("common.paused")}`}</p>
    {attempt.scope === "FOCUSED_UNIT" ? <p>{t("runner.focusedPaused")}</p> : null}
    <h1>{t("runner.paused")}</h1>
    <p>{testTitle}</p>
    {attempt.focused_unit?.title ? <p>{focusedUnitLabel(attempt, t)}</p> : null}
    <p>{t("runner.progressSaved")}</p>
    {recoveredIds.length ? <section className="notice" aria-label={t("runner.recoveredResponses")}>
      <strong>{t("runner.unsavedResponses")}</strong>
      {recoveredIds.map((id) => <p key={id}><b>{responseLabels.get(id) ?? t("runner.response")}:</b> {Array.isArray(values[id]) ? values[id].join(", ") : String(values[id] ?? "")}</p>)}
      <p>{t("runner.resumeToSave")}</p>
    </section> : null}
    <DraftRecoveryNotices offline={false} conflicts={conflicts} labelFor={(id) => responseLabels.get(id) ?? t("runner.responseLower")} onResolve={resolveConflict} />
    <strong>{frozenTime}</strong>
    {error ? <p role="alert" className="notice notice-error">{typeof error === "string" ? error : t(error.message)}</p> : null}
    <div>
      <button type="button" className="btn btn-primary" disabled={pending} onClick={() => void resume()}>{pending ? t("runner.resuming") : t("runner.resumeAttempt")}</button>
      <Link href="/history" className="btn btn-secondary">{t("runner.backHistory")}</Link>
    </div>
  </main>;
}

function questionLabel(type: string, start: number, config: Record<string, unknown>, t: TranslationFunction): string {
  const end = start + questionSpan(type, config) - 1;
  return end === start ? t("runner.question", { number: start }) : t("common.questionsRange", { start, end });
}
