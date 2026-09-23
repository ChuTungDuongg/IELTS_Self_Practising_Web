import { PageHeading } from "@/components/ui/page-heading";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { getAnalytics } from "@/lib/api/analytics";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const data = await getAnalytics(undefined, serverApiRequest).catch(() => ({ total_finalized_attempts: 0, total_active_seconds: 0, average_attempt_seconds: null, bands: { READING: { latest: null, best: null, average: null }, LISTENING: { latest: null, best: null, average: null }, WRITING: { latest: null, best: null, average: null } }, completed_full_mocks: 0, latest_project_overall: null, latest_full_mock: null, trends: [], question_types: [], weak_areas: [], attempts: [], content_timing: [] }));
  return <><PageHeading eyebrow="Progress" title="Analytics" description="Understand how your practice is changing over time." /><AnalyticsDashboardView initial={data} /></>;
}
