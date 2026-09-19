"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
        <ul className="divide-y divide-[var(--line)]">
          {items.map((item) => (
            <li
              key={item.attempt_id}
              className="flex flex-wrap items-center gap-4 px-6 py-5 transition-colors hover:bg-[var(--surface-soft)]"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{item.test_title}</p>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {item.module} · Version {item.version_number} ·{" "}
                  {new Date(item.started_at).toLocaleString()}
                </p>
              </div>
              <StatusBadge status={item.status} />
              <span className="w-20 text-right text-sm tabular-nums text-[var(--muted)]">
                {item.elapsed_seconds === null ? "—" : formatDuration(item.elapsed_seconds)}
              </span>
              {item.status !== "IN_PROGRESS" ? (
                <Link
                  href={`/review/${item.attempt_id}`}
                  className="text-sm font-semibold text-[var(--accent)]"
                >
                  Review
                </Link>
              ) : (
                <Link
                  href={`/attempt/${item.attempt_id}`}
                  className="text-sm font-semibold text-[var(--accent)]"
                >
                  Continue
                </Link>
              )}
              <button
                type="button"
                disabled={pending}
                aria-label={`Delete ${item.test_title}`}
                onClick={() => chooseAttempt(item)}
                className="btn btn-danger-ghost"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="p-8 text-center text-[var(--muted)]">No attempts have been recorded.</p>
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
