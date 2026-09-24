"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { formatDuration } from "@/features/exam/timer";
import { resumeAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { ExamPayload } from "@/lib/api/exam";
import { useExamDraftAutosave } from "./use-exam-draft-autosave";
import { DraftRecoveryNotices } from "./draft-recovery-notices";

const pausedSave = async (): Promise<never> => { throw new Error("Resume before saving responses."); };

export function PausedAttemptGate({ exam }: { exam: ExamPayload }) {
  const { attempt, test_title: testTitle } = exam;
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const responseLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const task of exam.writing_tasks ?? []) labels.set(task.id, `Task ${task.task_number}`);
    for (const passage of exam.passages ?? []) for (const group of passage.question_groups) for (const question of group.questions) labels.set(question.id, `Question ${question.number}`);
    for (const part of exam.listening_parts ?? []) for (const group of part.question_groups) for (const question of group.questions) labels.set(question.id, `Question ${question.number}`);
    return labels;
  }, [exam]);
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
      setError(caught instanceof ApiError ? caught.message : "This attempt could not be resumed. Please try again.");
      setPending(false);
    }
  }

  const frozenTime = attempt.timer_mode === "COUNTDOWN"
    ? `Remaining: ${formatDuration(attempt.remaining_seconds ?? 0)}`
    : `Practice time: ${formatDuration(attempt.elapsed_seconds)}`;

  return <main className="paused-attempt-gate">
    <p className="page-eyebrow">{attempt.module} · PAUSED</p>
    <h1>Attempt paused</h1>
    <p>{testTitle}</p>
    <p>Your progress is saved.</p>
    {recoveredIds.length ? <section className="notice" aria-label="Recovered responses from this tab">
      <strong>Unsaved responses kept in this tab</strong>
      {recoveredIds.map((id) => <p key={id}><b>{responseLabels.get(id) ?? "Response"}:</b> {Array.isArray(values[id]) ? values[id].join(", ") : String(values[id] ?? "")}</p>)}
      <p>Resume to save these responses.</p>
    </section> : null}
    <DraftRecoveryNotices offline={false} conflicts={conflicts} labelFor={(id) => responseLabels.get(id) ?? "response"} onResolve={resolveConflict} />
    <strong>{frozenTime}</strong>
    {error ? <p role="alert" className="notice notice-error">{error}</p> : null}
    <div>
      <button type="button" className="btn btn-primary" disabled={pending} onClick={() => void resume()}>{pending ? "Resuming…" : "Resume attempt"}</button>
      <Link href="/history" className="btn btn-secondary">Back to history</Link>
    </div>
  </main>;
}
