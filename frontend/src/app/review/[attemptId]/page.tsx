import { notFound } from "next/navigation";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { WritingReviewView } from "@/features/writing/writing-review";
import { getExam, getListeningReview, getReadingReview, getWritingReview } from "@/lib/api/exam";
import { serverApiRequest } from "@/lib/api/server-client";
import { AttemptDraftCleanup } from "@/features/exam/attempt-draft-cleanup";
import { isTerminalAttempt } from "@/features/exam/exam-draft-recovery";

export default async function ReviewShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const exam = await getExam(attemptId, serverApiRequest).catch(() => null);
  if (!exam) notFound();
  if (exam.attempt.module === "WRITING") {
    const writing = await getWritingReview(attemptId, serverApiRequest).catch(() => null);
    if (!writing) notFound();
    return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<WritingReviewView data={writing} /></>;
  }
  if (exam.attempt.module === "LISTENING") {
    const listening = await getListeningReview(attemptId, serverApiRequest).catch(() => null);
    if (!listening) notFound();
    return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<ListeningReviewView data={listening} /></>;
  }
  const review = await getReadingReview(attemptId, serverApiRequest).catch(() => null);
  if (!review) notFound();
  return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<ReadingReviewView data={review} /></>;
}
