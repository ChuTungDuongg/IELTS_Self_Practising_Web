import Link from "next/link";
import { getAssignmentResult, listAssignmentResults } from "@/lib/api/classroom-results";
import { serverApiRequest } from "@/lib/api/server-client";
import { PageHeading } from "@/components/ui/page-heading";
import { UiText } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
import { TeacherResultView } from "./teacher-result-view";
import { GOVERNANCE_PAGE_SIZE, pageOffset } from "@/lib/api/pagination";
import { PageNavigation } from "./page-navigation";
export async function ClassroomResultsPage({ params, namespace = "teacher", searchParams }: {
  params: Promise<{
    classroomId: string;
    assignmentId: string;
  }>;
  namespace?: "teacher" | "shared";
  searchParams?: Promise<{ offset?: string; }>;
}) {
  const { classroomId, assignmentId } = await params;
  const offset = pageOffset((await searchParams)?.offset);
  const page = await listAssignmentResults(classroomId, assignmentId, serverApiRequest, { limit: GOVERNANCE_PAGE_SIZE + 1, offset });
  const items = page.slice(0, GOVERNANCE_PAGE_SIZE);
  const prefix = namespace === "teacher" ? "/teacher" : "";
  return <>
    <PageHeading title={<UiText message="assignment.results" />} description={<UiText message="assignment.readOnly" />} />
    {items.length ? <div className="test-card-grid">
      {items.map(item => <article key={item.attempt.attempt_id} className="surface-card p-5">
        <h2>{item.student_display_name}</h2>
        <p>
          <UiText message={moduleTranslationKeys[item.attempt.module]} /> · <UiText message={statusTranslationKeys[item.attempt.status]} />
        </p>
        <p>{item.attempt.band_score ?? item.attempt.raw_score ?? "—"}</p>
        <Link className="btn btn-secondary mt-3" href={`${prefix}/classrooms/${classroomId}/assignments/${assignmentId}/results/${item.attempt.attempt_id}`}>
          <UiText message="common.open" />
        </Link>
      </article>)}
    </div> : <p>
      <UiText message="assignment.noResults" />
    </p>}
    <PageNavigation path={`${prefix}/classrooms/${classroomId}/assignments/${assignmentId}/results`} offset={offset} hasNext={page.length > GOVERNANCE_PAGE_SIZE} />
  </>;
}
export async function ClassroomResultPage({ params }: {
  params: Promise<{
    classroomId: string;
    assignmentId: string;
    attemptId: string;
  }>;
}) {
  const { classroomId, assignmentId, attemptId } = await params;
  return <TeacherResultView data={await getAssignmentResult(classroomId, assignmentId, attemptId, serverApiRequest)} />;
}
