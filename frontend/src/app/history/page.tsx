import { UiText } from "@/lib/i18n/locale-provider";
import { PageHeading } from "@/components/ui/page-heading";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { getHistory } from "@/lib/api/history";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const history = await getHistory(serverApiRequest).catch(() => ({ items: [], groups: [], sessions: [], total: 0 }));
  return (
    <>
      <PageHeading eyebrow={<UiText message="pages.record" />} eyebrowClassName="history-eyebrow" title={<UiText message="pages.history" />} description={<UiText message="pages.historyDescription" />} />
      <div className="history-surface">
        <AttemptHistoryList initialHistory={history} />
      </div>
    </>
  );
}
