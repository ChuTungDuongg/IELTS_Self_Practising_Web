import { notFound } from "next/navigation";
import { ReadingReviewView } from "@/features/reading/reading-review";
import { getReadingReview } from "@/lib/api/exam";

export default async function ReviewShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const review = await getReadingReview(attemptId).catch(() => null);
  if (!review) notFound();
  return <ReadingReviewView data={review} />;
}
