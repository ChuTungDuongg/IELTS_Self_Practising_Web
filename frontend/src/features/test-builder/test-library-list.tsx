"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ArchiveIcon, ArrowIcon, BuilderIcon, SearchIcon } from "@/components/ui/icons";
import { StatusBadge } from "@/components/ui/status-badge";
import { ApiError } from "@/lib/api/client";
import type { TestSummary } from "@/lib/api/schema";
import { cloneVersion, deleteTest, permanentlyDeleteTest, restoreTest } from "@/lib/api/tests";
import { builderEditPath } from "@/lib/routes";

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
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<TestSummary | null>(null);
  const [permanentSelected, setPermanentSelected] = useState<TestSummary | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
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
        setArchivedTests((current) => [{ ...target, archived_at: new Date().toISOString() }, ...current]);
        setMessage({ kind: "success", text: `Archived “${target.title}”.` });
      } else {
        setMessage({ kind: "success", text: `Deleted “${target.title}”.` });
      }
      setSelected(null);
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : "The test could not be removed." });
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
      setMessage({ kind: "success", text: `Restored “${target.title}”.` });
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : "The test could not be restored." });
    } finally {
      setPendingId(null);
    }
  }

  async function editPublished(target: TestSummary) {
    if (pendingId) return;
    const published = [...target.versions].reverse().find((version) => version.status === "PUBLISHED");
    if (!published) return;
    setPendingId(target.id);
    try {
      const draft = await cloneVersion(target.id, published.id);
      router.push(builderEditPath(target.id, draft.id));
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : "The draft could not be opened." });
      setPendingId(null);
    }
  }

  async function permanentlyRemove() {
    if (!permanentSelected || pendingId) return;
    const target = permanentSelected;
    setPendingId(target.id);
    try {
      await permanentlyDeleteTest(target.id);
      setArchivedTests((current) => current.filter((item) => item.id !== target.id));
      setPermanentSelected(null);
      setMessage({ kind: "success", text: `Permanently deleted “${target.title}” and its attempt history.` });
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : "The test could not be permanently deleted." });
    } finally {
      setPendingId(null);
    }
  }

  const visibleTests = view === "active" ? activeTests : archivedTests;
  const filteredTests = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return visibleTests;
    return visibleTests.filter((test) => `${test.title} ${test.description ?? ""}`.toLocaleLowerCase().includes(normalized));
  }, [query, visibleTests]);

  return (
    <>
      <div className="library-toolbar surface-card">
        <div className="segmented-control" role="tablist" aria-label="Test status">
          <button type="button" role="tab" aria-selected={view === "active"} onClick={() => setView("active")}>
            Active <span>({activeTests.length})</span>
          </button>
          <button type="button" role="tab" aria-selected={view === "archived"} onClick={() => setView("archived")}>
            Archived <span>({archivedTests.length})</span>
          </button>
        </div>
        <label className="library-search">
          <SearchIcon className="size-4" />
          <span className="sr-only">Search tests</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tests…" />
          {query ? <button type="button" onClick={() => setQuery("")} aria-label="Clear search">×</button> : null}
        </label>
      </div>

      {message ? (
        <p role={message.kind === "error" ? "alert" : "status"} className={`notice mt-4 ${message.kind === "error" ? "notice-error" : "notice-success"}`}>
          {message.text}
        </p>
      ) : null}

      {filteredTests.length ? (
        <div className={`test-card-grid ${view === "archived" ? "archived-grid" : ""}`}>
          {filteredTests.map((test) => {
            const latest = test.versions.at(-1);
            const draft = [...test.versions].reverse().find((version) => version.status === "DRAFT");
            const published = [...test.versions].reverse().find((version) => version.status === "PUBLISHED");
            const destructiveLabel = hasHistory(test) ? "Archive" : "Delete";
            return (
              <article key={test.id} className="test-card">
                <div className="test-card-accent" aria-hidden="true" />
                <div className="test-card-topline">
                  <span className="test-type"><BuilderIcon className="size-4" /> IELTS test</span>
                  {latest ? <StatusBadge status={view === "archived" ? "ARCHIVED" : latest.status} /> : null}
                </div>
                <div className="test-card-title">
                  <h2>{test.title}</h2>
                  <p>{test.description || "No description has been added yet."}</p>
                </div>
                <div className="test-card-stats">
                  <div><strong>{test.versions.length}</strong><span>Version{test.versions.length === 1 ? "" : "s"}</span></div>
                  <div><strong>{test.versions.filter((version) => version.status === "PUBLISHED").length}</strong><span>Published</span></div>
                  <div><strong>{draft ? "Yes" : "—"}</strong><span>Open draft</span></div>
                </div>
                <div className="test-card-meta">
                  <span>Updated {formatUpdated(test.updated_at)}</span>
                  {latest ? <span>Latest · v{latest.version_number}</span> : <span>No versions</span>}
                </div>
                <div className="test-card-actions">
                  <Link href={`/admin/tests/${test.id}`} className="btn btn-secondary">Open</Link>
                  {view === "active" && draft ? (
                    <Link href={builderEditPath(test.id, draft.id)} className="btn btn-primary">
                      Continue draft <ArrowIcon className="size-4" />
                    </Link>
                  ) : view === "active" && published ? (
                    <button type="button" disabled={pendingId !== null} onClick={() => void editPublished(test)} className="btn btn-primary">Edit <ArrowIcon className="size-4" /></button>
                  ) : view === "archived" ? (
                    <button type="button" disabled={pendingId !== null} aria-label={`Restore ${test.title}`} onClick={() => void restore(test)} className="btn btn-primary">
                      Restore
                    </button>
                  ) : null}
                  {view === "active" ? (
                    <button type="button" disabled={pendingId !== null} aria-label={`${destructiveLabel} ${test.title}`} onClick={() => setSelected(test)} className="btn btn-danger-ghost ml-auto">
                      {destructiveLabel}
                    </button>
                  ) : <button type="button" disabled={pendingId !== null} aria-label={`Delete permanently ${test.title}`} onClick={() => setPermanentSelected(test)} className="btn btn-danger-ghost ml-auto">Delete permanently</button>}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mt-5">
          <EmptyState
            icon={view === "archived" ? <ArchiveIcon className="size-6" /> : undefined}
            title={query ? "No matching tests" : view === "active" ? "Your builder is ready" : "Archive is empty"}
            description={query ? "Try a different title or clear the search." : view === "active" ? "Create the first test to start building structured IELTS content." : "Tests you archive will remain safely available here for restoration."}
          />
        </div>
      )}

      <ConfirmDialog
        open={selected !== null}
        title={selectedWillArchive ? `Archive “${selected?.title ?? ""}”?` : `Delete “${selected?.title ?? ""}”?`}
        description={selectedWillArchive ? "Published versions and attempt history will be preserved. You can restore this test later." : "This action cannot be undone."}
        confirmLabel={selectedWillArchive ? "Archive" : "Delete"}
        pending={pendingId !== null}
        onCancel={() => setSelected(null)}
        onConfirm={() => void removeSelected()}
      />
      <ConfirmDialog open={permanentSelected !== null} title={`Delete “${permanentSelected?.title ?? ""}” permanently?`} description="Deleting this test permanently will also delete all attempt history for this test. This action cannot be undone." confirmLabel="Delete permanently" pending={pendingId !== null} onCancel={() => setPermanentSelected(null)} onConfirm={() => void permanentlyRemove()} />
    </>
  );
}

function hasHistory(test: TestSummary): boolean {
  return test.versions.some((version) => version.status === "PUBLISHED" || version.status === "ARCHIVED");
}

function formatUpdated(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}
