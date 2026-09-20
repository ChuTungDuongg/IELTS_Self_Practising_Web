"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { HistoryIcon } from "@/components/ui/icons";
import { ModuleBadge } from "@/components/ui/module-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDuration } from "@/features/exam/timer";
import { deleteAttempt } from "@/lib/api/attempts";
import { ApiError } from "@/lib/api/client";
import type { HistoryItem } from "@/lib/api/history";

export function AttemptHistoryList({ initialItems }: { initialItems: HistoryItem[] }) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [selected, setSelected] = useState<HistoryItem | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  function chooseAttempt(item: HistoryItem) {
    setSelected(item);
    setError(undefined);
  }

  function cancelDelete() {
    if (pending) return;
    setSelected(null);
    setError(undefined);
  }

  async function confirmDelete() {
    if (!selected || pending) return;
    setPending(true);
    setError(undefined);
    try {
      await deleteAttempt(selected.attempt_id);
      setItems((current) => current.filter((item) => item.attempt_id !== selected.attempt_id));
      setSelected(null);
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "The attempt could not be deleted. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      {items.length ? (
        <ul className="history-list">
          {items.map((item) => (
            <li
              key={item.attempt_id}
              className="history-row"
            >
              <div className="history-record">
                <div className="history-record-topline"><ModuleBadge module={item.module} /><span>Version {item.version_number}</span></div>
                <p className="history-record-title">{item.test_title}</p>
                <p className="history-record-date">Started {new Date(item.started_at).toLocaleString()}</p>
              </div>
              <div className="history-state">
                <StatusBadge status={item.status} />
                <span className="history-duration">
                  {item.elapsed_seconds === null ? "Time in progress" : formatDuration(item.elapsed_seconds)}
                </span>
              </div>
              <div className="history-actions">
                {item.status !== "IN_PROGRESS" ? (
                  <Link href={`/review/${item.attempt_id}`} className="btn btn-primary">Review</Link>
                ) : (
                  <Link href={`/attempt/${item.attempt_id}`} className="btn btn-primary">Continue</Link>
                )}
                <button type="button" disabled={pending} aria-label={`Delete ${item.test_title}`} onClick={() => chooseAttempt(item)} className="btn btn-danger-ghost">Delete</button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={<HistoryIcon className="size-6" />} title="No practice attempts yet" description="Start a published Reading or Listening test and your saved progress will appear here." />
      )}

      <ConfirmDialog
        open={selected !== null}
        title="Delete this attempt?"
        description={`${selected?.status === "IN_PROGRESS" ? "This attempt is still in progress. " : ""}This will permanently remove this attempt and its saved answers, highlights, flags and activity history. The test itself will not be deleted.`}
        confirmLabel="Delete attempt"
        pending={pending}
        errorMessage={error}
        onCancel={cancelDelete}
        onConfirm={() => void confirmDelete()}
      />
    </>
  );
}
