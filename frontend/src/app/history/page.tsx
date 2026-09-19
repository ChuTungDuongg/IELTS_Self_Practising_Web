import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { getHistory } from "@/lib/api/history";
import { formatDuration } from "@/features/exam/timer";

export const dynamic = "force-dynamic";

export default async function HistoryPage() {
  const history = await getHistory().catch(() => ({ items: [], total: 0 }));
  return (
    <>
      <PageHeading eyebrow="Practice record" title="Attempt history" description="Every attempt remains attached to its exact frozen test version." />
      <div className="surface-card overflow-hidden">
        {history.items.length ? (
          <ul className="divide-y divide-[var(--line)]">
            {history.items.map((item) => (
              <li key={item.attempt_id} className="flex flex-wrap items-center gap-4 px-6 py-5 transition-colors hover:bg-[var(--surface-soft)]">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{item.test_title}</p>
                  <p className="mt-1 text-sm text-[var(--muted)]">
                    {item.module} · Version {item.version_number} · {new Date(item.started_at).toLocaleString()}
                  </p>
                </div>
                <StatusBadge status={item.status} />
                <span className="w-20 text-right text-sm tabular-nums text-[var(--muted)]">
                  {item.elapsed_seconds === null ? "—" : formatDuration(item.elapsed_seconds)}
                </span>
                {item.status !== "IN_PROGRESS" ? (
                  <Link href={`/review/${item.attempt_id}`} className="text-sm font-semibold text-[var(--accent)]">
                    Review
                  </Link>
                ) : (
                  <Link href={`/attempt/${item.attempt_id}`} className="text-sm font-semibold text-[var(--accent)]">
                    Continue
                  </Link>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="p-8 text-center text-[var(--muted)]">No attempts have been recorded.</p>
        )}
      </div>
    </>
  );
}
