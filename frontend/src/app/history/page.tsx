import { PageHeading } from "@/components/ui/page-heading";
import { AttemptHistoryList } from "@/features/history/attempt-history-list";
import { getHistory } from "@/lib/api/history";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const history = await getHistory().catch(() => ({ items: [], groups: [], total: 0 }));
  return (
    <>
      <PageHeading eyebrow="Practice record" title="Attempt history" description="Every attempt remains attached to its exact frozen test version." />
      <div className="history-surface">
        <AttemptHistoryList initialHistory={history} />
      </div>
    </>
  );
}
