import { SpeakingReview } from "@/features/speaking/speaking-review";
import { getSpeakingReview } from "@/lib/api/speaking";
import { notFound } from "next/navigation";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { WritingReviewView } from "@/features/writing/writing-review";
import { getExam, getListeningReview, getReadingReview, getWritingReview } from "@/lib/api/exam";
import { serverApiRequest } from "@/lib/api/server-client";
import { ApiError } from "@/lib/api/client";
import { AttemptDraftCleanup } from "@/features/exam/attempt-draft-cleanup";
import { isTerminalAttempt } from "@/features/exam/exam-draft-recovery";

async function availableReview<T>(load: () => Promise<T>): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (error instanceof ApiError && (
      error.status === 401 || error.status === 403 || error.status === 404 ||
      error.code === "FULL_MOCK_REVIEW_LOCKED" || error.code === "ATTEMPT_NOT_FINALIZED"
    )) notFound();
    throw error;
  }
}

export default async function ReviewShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const exam = await availableReview(() => getExam(attemptId, serverApiRequest));
  if (exam.attempt.module === "SPEAKING") {
    const data = await availableReview(() => getSpeakingReview(attemptId, serverApiRequest));
    return <SpeakingReview data={data} />;
  }
  if (exam.attempt.module === "WRITING") {
    const writing = await availableReview(() => getWritingReview(attemptId, serverApiRequest));
    return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<WritingReviewView data={writing} /></>;
  }
  if (exam.attempt.module === "LISTENING") {
    const listening = await availableReview(() => getListeningReview(attemptId, serverApiRequest));
    return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<ListeningReviewView data={listening} /></>;
  }
  const review = await availableReview(() => getReadingReview(attemptId, serverApiRequest));
  return <>{isTerminalAttempt(exam.attempt.status) ? <AttemptDraftCleanup attemptId={attemptId} /> : null}<ReadingReviewView data={review} /></>;
}
