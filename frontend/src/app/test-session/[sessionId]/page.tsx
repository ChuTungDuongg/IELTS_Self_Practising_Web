import { notFound, redirect } from "next/navigation";
import { TestSessionTransition } from "@/features/exam/test-session-transition";
import { getTestSession } from "@/lib/api/test-sessions";

export const dynamic = "force-dynamic";

export default async function TestSessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  const session = await getTestSession(sessionId).catch(() => null);
  if (!session) notFound();
  if (session.current_attempt) redirect(`/attempt/${session.current_attempt.attempt_id}`);
  return <TestSessionTransition initial={session} />;
}
