import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { getAnalytics } from "@/lib/api/analytics";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const data = await getAnalytics(undefined, serverApiRequest);
  return <AnalyticsDashboardView initial={data} asOf={new Date().toISOString()} />;
}
