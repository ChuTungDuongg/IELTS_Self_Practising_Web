import { AdminGuard } from "@/features/auth/admin-guard";
import { ResearchDetail } from "@/features/speaking-benchmark/research/research-detail";

export default async function Page({ params, searchParams }: { params: Promise<{ experimentId: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { experimentId } = await params; const query = await searchParams;
  const keys = ["split", "part", "provider_key", "min_duration_ms", "max_duration_ms", "accent", "speaking_speed", "response_length", "human_overall", "latest_references"];
  const initialFilters = Object.fromEntries(Object.entries(query).filter(([key, value]) => keys.includes(key) && typeof value === "string")) as Record<string, string>;
  return <AdminGuard><ResearchDetail experimentId={experimentId} initialFilters={initialFilters} /></AdminGuard>;
}
