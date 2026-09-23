import { notFound } from "next/navigation";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { WritingRunner } from "@/features/writing/writing-runner";
import { getExam } from "@/lib/api/exam";
import { PausedAttemptGate } from "@/features/exam/paused-attempt-gate";
import { serverApiRequest } from "@/lib/api/server-client";

export default async function AttemptShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  const exam = await getExam(attemptId, serverApiRequest).catch(() => null);
  if (!exam) notFound();
  if (exam.attempt.status === "PAUSED") {
    return <PausedAttemptGate attempt={exam.attempt} testTitle={exam.test_title} />;
  }
  if (exam.attempt.module === "WRITING") return <WritingRunner initial={exam} />;
  return exam.attempt.module === "LISTENING" ? <ListeningRunner initial={exam} /> : <ReadingRunner initial={exam} />;
}
