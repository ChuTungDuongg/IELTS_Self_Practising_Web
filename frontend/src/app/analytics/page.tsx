import { UiText } from "@/lib/i18n/locale-provider";
import { PageHeading } from "@/components/ui/page-heading";
import { AnalyticsDashboardView } from "@/features/analytics/analytics-dashboard";
import { getAnalytics } from "@/lib/api/analytics";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function AnalyticsPage() {
  const data = await getAnalytics(undefined, serverApiRequest);
  return <><PageHeading eyebrow={<UiText message="pages.progress" />} title={<UiText message="pages.analytics" />} description={<UiText message="pages.analyticsDescription" />} /><AnalyticsDashboardView initial={data} /></>;
}
