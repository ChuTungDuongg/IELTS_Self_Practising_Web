import { AdminGuard } from "@/features/auth/admin-guard";
import { SpeakingBenchmarkDetail } from "@/features/speaking-benchmark/sample-detail";

export default async function SpeakingBenchmarkSamplePage({ params }: { params: Promise<{ sampleId: string }> }) {
  const { sampleId } = await params;
  return <AdminGuard><SpeakingBenchmarkDetail sampleId={sampleId} /></AdminGuard>;
}
