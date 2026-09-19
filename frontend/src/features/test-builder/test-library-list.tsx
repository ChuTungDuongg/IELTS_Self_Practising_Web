"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api/client";
import type { TestSummary } from "@/lib/api/schema";
import { deleteTest, restoreTest } from "@/lib/api/tests";

export function TestLibraryList({
  activeTests: initialActiveTests,
  archivedTests: initialArchivedTests,
}: {
  activeTests: TestSummary[];
  archivedTests: TestSummary[];
}) {
  const router = useRouter();
  const [activeTests, setActiveTests] = useState(initialActiveTests);
  const [archivedTests, setArchivedTests] = useState(initialArchivedTests);
  const [view, setView] = useState<"active" | "archived">("active");
  const [selected, setSelected] = useState<TestSummary | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const selectedWillArchive = selected ? hasHistory(selected) : false;

  async function removeSelected() {
    if (!selected || pendingId) return;
    const target = selected;
    setPendingId(target.id);
    setMessage(null);
    try {
      const result = await deleteTest(target.id);
      setActiveTests((current) => current.filter((item) => item.id !== target.id));
      if (result.action === "ARCHIVED") {
        setArchivedTests((current) => [
          { ...target, archived_at: new Date().toISOString() },
          ...current,
        ]);
        setMessage(`Archived “${target.title}”.`);
      } else {
        setMessage(`Deleted “${target.title}”.`);
      }
      setSelected(null);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The test could not be removed.");
    } finally {
      setPendingId(null);
    }
  }

  async function restore(target: TestSummary) {
    if (pendingId) return;
    setPendingId(target.id);
    setMessage(null);
    try {
      const restored = await restoreTest(target.id);
      setArchivedTests((current) => current.filter((item) => item.id !== target.id));
      setActiveTests((current) => [restored, ...current]);
      setMessage(`Restored “${target.title}”.`);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The test could not be restored.");
    } finally {
      setPendingId(null);
    }
  }

  const visibleTests = view === "active" ? activeTests : archivedTests;

  return (
    <>
      <div className="mb-4 flex gap-2" role="tablist" aria-label="Test status">
        <button
          type="button"
          role="tab"
          aria-selected={view === "active"}
          onClick={() => setView("active")}
          className={`rounded-md px-3 py-2 text-sm font-semibold ${view === "active" ? "bg-[var(--accent)] text-white" : "border border-[var(--line)] bg-[var(--surface)]"}`}
        >
          Active ({activeTests.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "archived"}
          onClick={() => setView("archived")}
          className={`rounded-md px-3 py-2 text-sm font-semibold ${view === "archived" ? "bg-[var(--accent)] text-white" : "border border-[var(--line)] bg-[var(--surface)]"}`}
        >
          Archived ({archivedTests.length})
        </button>
      </div>

      {message ? (
        <p role={message.includes("could not") ? "alert" : "status"} className="mb-4 text-sm text-[var(--muted)]">
          {message}
        </p>
      ) : null}

      <div className="space-y-3">
        {visibleTests.map((test) => {
          const draft = [...test.versions].reverse().find((version) => version.status === "DRAFT");
          const destructiveLabel = hasHistory(test) ? "Archive" : "Delete";
          return (
            <article
              key={test.id}
              className="flex flex-wrap items-center gap-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-5"
            >
              <div className="min-w-0 flex-1">
                <h2 className="truncate font-semibold">{test.title}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  {test.versions.length} version{test.versions.length === 1 ? "" : "s"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {test.versions.slice(-3).map((version) => (
                  <StatusBadge key={version.id} status={version.status} />
                ))}
                <Link
                  href={`/admin/tests/${test.id}`}
                  className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-semibold"
                >
                  Open
                </Link>
                {view === "active" && draft ? (
                  <Link
                    href={`/admin/tests/${test.id}/versions/${draft.id}/edit`}
                    className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-semibold"
                  >
                    Continue draft
                  </Link>
                ) : null}
                {view === "active" ? (
                  <button
                    type="button"
                    disabled={pendingId !== null}
                    aria-label={`${destructiveLabel} ${test.title}`}
                    onClick={() => setSelected(test)}
                    className="rounded-md px-3 py-2 text-sm font-semibold text-red-700 disabled:opacity-50"
                  >
                    {destructiveLabel}
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={pendingId !== null}
                    aria-label={`Restore ${test.title}`}
                    onClick={() => void restore(test)}
                    className="rounded-md border border-[var(--line)] px-3 py-2 text-sm font-semibold text-[var(--accent)] disabled:opacity-50"
                  >
                    Restore
                  </button>
                )}
              </div>
            </article>
          );
        })}
        {!visibleTests.length ? (
          <p className="rounded-xl border border-dashed border-[var(--line)] p-8 text-center text-[var(--muted)]">
            {view === "active" ? "No tests yet. Create the first draft." : "No archived tests."}
          </p>
        ) : null}
      </div>

      <ConfirmDialog
        open={selected !== null}
        title={
          selectedWillArchive
            ? `Archive “${selected?.title ?? ""}”?`
            : `Delete “${selected?.title ?? ""}”?`
        }
        description={
          selectedWillArchive
            ? "Published versions and attempt history will be preserved. You can restore this test later."
            : "This action cannot be undone."
        }
        confirmLabel={selectedWillArchive ? "Archive" : "Delete"}
        pending={pendingId !== null}
        onCancel={() => setSelected(null)}
        onConfirm={() => void removeSelected()}
      />
    </>
  );
}

function hasHistory(test: TestSummary): boolean {
  return test.versions.some(
    (version) => version.status === "PUBLISHED" || version.status === "ARCHIVED",
  );
}
