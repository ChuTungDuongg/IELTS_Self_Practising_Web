import { AdminGuard } from "@/features/auth/admin-guard";
import { AssignedReviews } from "@/features/speaking-benchmark/assigned-reviews";

export default function AssignedReviewsPage() {
  return <AdminGuard><AssignedReviews /></AdminGuard>;
}
