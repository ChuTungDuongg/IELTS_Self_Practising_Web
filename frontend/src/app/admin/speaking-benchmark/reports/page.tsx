import { AdminGuard } from "@/features/auth/admin-guard";
import { SpeakingBenchmarkReports } from "@/features/speaking-benchmark/evaluation/reports";

export default function Page() { return <AdminGuard><SpeakingBenchmarkReports /></AdminGuard>; }
