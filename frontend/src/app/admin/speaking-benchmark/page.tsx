import { AdminGuard } from "@/features/auth/admin-guard";
import { SpeakingBenchmarkList } from "@/features/speaking-benchmark/sample-list";

export default function SpeakingBenchmarkPage() {
  return <AdminGuard><SpeakingBenchmarkList /></AdminGuard>;
}
