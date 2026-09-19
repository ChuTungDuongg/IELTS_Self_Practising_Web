import { notFound } from "next/navigation";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { getExam } from "@/lib/api/exam";

export default async function AttemptShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const exam = await getExam(attemptId).catch(() => null);
  if (!exam) notFound();
  return exam.attempt.module === "LISTENING" ? <ListeningRunner initial={exam} /> : <ReadingRunner initial={exam} />;
}
