"use client";

import { ReadingReviewView } from "@/features/reading/reading-review";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { WritingReviewView } from "@/features/writing/writing-review";
import { CriterionAssessmentCard } from "@/features/writing/writing-ai-criterion-card";
import { WritingRelevanceNotice } from "@/features/writing/writing-ai-practice-feedback";
import { aiTraits } from "@/lib/api/writing-ai";
import type { AssignmentResultDetail } from "@/lib/api/classroom-results";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
export function TeacherResultView({ data }: {
  data: AssignmentResultDetail;
}) {
  const { t } = useTranslation();
  return <>
    <p className="notice mb-5">{t("assignment.readOnly")}</p>
    <h1>{data.student_display_name} · {t(moduleTranslationKeys[data.attempt.module])}</h1>
    <p>{t(statusTranslationKeys[data.attempt.status])}</p>
    <dl className="surface-card p-5 my-5">
      <div>
        <dt>{t("assignment.started")}</dt>
        <dd>{data.attempt.started_at}</dd>
      </div>
      <div>
        <dt>{t("assignment.finished")}</dt>
        <dd>{data.attempt.finished_at ?? "—"}</dd>
      </div>
    </dl>
    {data.reading_review ? <ReadingReviewView data={data.reading_review} /> : null}
    {data.listening_review ? <ListeningReviewView data={data.listening_review} /> : null}
    {data.writing_review ? <WritingReviewView data={data.writing_review} readOnly /> : null}
    {!data.reading_review && !data.listening_review && !data.writing_review ? <section className="surface-card p-5">
      <h2>{t("runner.savedResponse")}</h2>{data.writing_responses.map(response => <article key={response.writing_task_id}>
        <h3>{t("common.taskNumber", { number: response.task_number })}</h3>
        <p className="whitespace-pre-wrap">{response.content}</p>
      </article>)}{data.submitted_answers.map(answer => <p key={answer.question_id}>{JSON.stringify(answer.value)}</p>)}</section> : null}
    {data.ai_runs.filter(run => run.result).map(run => <section key={run.id} className="surface-card p-5 my-5">
      <h2>{t("writingAI.advisoryBadge")}</h2>
      <WritingRelevanceNotice relevance={run.result?.relevance} />
      <div className="writing-criteria-grid">{aiTraits.map(trait => <CriterionAssessmentCard key={trait} trait={trait} assessment={run.result!.criteria[trait]} taskNumber={run.result!.task_number ?? 2} visualAnalysis={run.result?.task_number === 1 ? run.result.task1_analysis : null} />)}</div>
    </section>)}
  </>;
}
