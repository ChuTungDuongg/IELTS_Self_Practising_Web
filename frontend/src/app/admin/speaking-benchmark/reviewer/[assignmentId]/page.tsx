import { AdminGuard } from "@/features/auth/admin-guard";
import { BlindReviewer } from "@/features/speaking-benchmark/blind-reviewer";

export default async function BlindReviewerPage({
  params,
}: {
  params: Promise<{ assignmentId: string }>;
}) {
  const { assignmentId } = await params;
  return (
    <AdminGuard>
      <BlindReviewer assignmentId={assignmentId} />
    </AdminGuard>
  );
}
