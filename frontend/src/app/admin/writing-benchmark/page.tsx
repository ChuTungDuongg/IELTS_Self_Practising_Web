import { AdminGuard } from "@/features/auth/admin-guard";
import { WritingBenchmarkBankPage } from "@/features/writing-benchmark/bank-page";

export default function WritingBenchmarkPage() {
  return <AdminGuard><WritingBenchmarkBankPage /></AdminGuard>;
}
