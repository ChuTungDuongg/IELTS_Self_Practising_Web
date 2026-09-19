import { notFound } from "next/navigation";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { ListeningReviewView } from "@/features/listening/listening-review";
import { getExam, getListeningReview, getReadingReview } from "@/lib/api/exam";

export default async function ReviewShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const exam = await getExam(attemptId).catch(() => null);
  if (!exam) notFound();
  if (exam.attempt.module === "LISTENING") {
    const listening = await getListeningReview(attemptId).catch(() => null);
    if (!listening) notFound();
    return <ListeningReviewView data={listening} />;
  }
  const review = await getReadingReview(attemptId).catch(() => null);
  if (!review) notFound();
  return <ReadingReviewView data={review} />;
}
