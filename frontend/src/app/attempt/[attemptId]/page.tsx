import { notFound, redirect } from "next/navigation";
import { ReadingRunner } from "@/features/reading/reading-runner";
import { ListeningRunner } from "@/features/listening/listening-runner";
import { WritingRunner } from "@/features/writing/writing-runner";
import { getExam } from "@/lib/api/exam";
import { PausedAttemptGate } from "@/features/exam/paused-attempt-gate";
import { serverApiRequest } from "@/lib/api/server-client";
import { ApiError } from "@/lib/api/client";
import { attemptDestination } from "@/features/exam/attempt-destination";

export default async function AttemptShellPage({ params }: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await params;
  let exam;
  try {
    exam = await getExam(attemptId, serverApiRequest);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    if (error instanceof ApiError && error.status === 401) redirect(`/login?next=${encodeURIComponent(`/attempt/${attemptId}`)}`);
    throw error;
  }
  if (exam.attempt.status === "PAUSED") {
    return <PausedAttemptGate attempt={exam.attempt} testTitle={exam.test_title} />;
  }
  if (exam.attempt.status !== "IN_PROGRESS") redirect(attemptDestination(exam.attempt));
  if (exam.attempt.module === "WRITING") return <WritingRunner initial={exam} />;
  return exam.attempt.module === "LISTENING" ? <ListeningRunner initial={exam} /> : <ReadingRunner initial={exam} />;
}
