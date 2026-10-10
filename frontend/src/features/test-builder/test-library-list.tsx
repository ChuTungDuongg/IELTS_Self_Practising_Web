"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { ArchiveIcon, ArrowIcon, BuilderIcon, SearchIcon } from "@/components/ui/icons";
import { StatusBadge } from "@/components/ui/status-badge";
import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";
import { statusTranslationKeys } from "@/lib/i18n/translations";
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
  const { t } = useTranslation();
  const router = useRouter();
  const [activeTests, setActiveTests] = useState(initialActiveTests);
  const [archivedTests, setArchivedTests] = useState(initialArchivedTests);
  const [view, setView] = useState<"active" | "archived">("active");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<TestSummary | null>(null);
  const [permanentSelected, setPermanentSelected] = useState<TestSummary | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string | { message: TranslationKey; params?: TranslationParams } } | null>(null);
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
        setMessage({ kind: "success", text: { message: "builder.archivedNamed", params: { title: target.title } } });
      } else {
        setMessage({ kind: "success", text: { message: "builder.deletedNamed", params: { title: target.title } } });
      }
      setSelected(null);
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : { message: "builder.removeFailed" } });
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
      setMessage({ kind: "success", text: { message: "builder.restoredNamed", params: { title: target.title } } });
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : { message: "builder.restoreFailed" } });
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
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : { message: "builder.openDraftFailed" } });
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
      setMessage({ kind: "success", text: { message: "builder.permanentlyDeletedNamed", params: { title: target.title } } });
      router.refresh();
    } catch (error) {
      setMessage({ kind: "error", text: error instanceof ApiError ? error.message : { message: "builder.permanentDeleteFailed" } });
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
        <div className="segmented-control" role="tablist" aria-label={t("builder.testStatus")}>
          <button type="button" role="tab" aria-selected={view === "active"} onClick={() => setView("active")}>
            {t("builder.activeTab")} <span>({activeTests.length})</span>
          </button>
          <button type="button" role="tab" aria-selected={view === "archived"} onClick={() => setView("archived")}>
            {t("common.archived")} <span>({archivedTests.length})</span>
          </button>
        </div>
        <label className="library-search">
          <SearchIcon className="size-4" />
          <span className="sr-only">{t("builder.search")}</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("builder.searchPlaceholder")} />
          {query ? <button type="button" onClick={() => setQuery("")} aria-label={t("common.clearSearch")}>×</button> : null}
        </label>
      </div>

      {message ? (
        <p role={message.kind === "error" ? "alert" : "status"} className={`notice mt-4 ${message.kind === "error" ? "notice-error" : "notice-success"}`}>
          {typeof message.text === "string" ? message.text : t(message.text.message, message.text.params)}
        </p>
      ) : null}

      {filteredTests.length ? (
        <div className={`test-card-grid ${view === "archived" ? "archived-grid" : ""}`}>
          {filteredTests.map((test) => {
            const latest = test.versions.at(-1);
            const draft = [...test.versions].reverse().find((version) => version.status === "DRAFT");
            const published = [...test.versions].reverse().find((version) => version.status === "PUBLISHED");
            const destructiveLabel = hasHistory(test) ? t("common.archive") : t("common.delete");
            return (
              <article key={test.id} className="test-card admin-test-card">
                <div className="test-card-accent" aria-hidden="true" />
                <div className="test-card-topline">
                  <span className="test-type"><BuilderIcon className="size-4" /> {t("builder.ieltsTest")}</span>
                  {latest ? <StatusBadge status={view === "archived" ? "ARCHIVED" : latest.status} label={t(statusTranslationKeys[view === "archived" ? "ARCHIVED" : latest.status])} /> : null}
                </div>
                <div className="test-card-title">
                  <h2>{test.title}</h2>
                  <p>{test.description || t("builder.descriptionEmpty")}</p>
                </div>
                <div className="test-card-stats">
                  <div><strong>{test.versions.length}</strong><span>{t(test.versions.length === 1 ? "builder.versionSingular" : "builder.versions")}</span></div>
                  <div><strong>{test.versions.filter((version) => version.status === "PUBLISHED").length}</strong><span>{t("common.published")}</span></div>
                  <div><strong>{draft ? t("common.yes") : "—"}</strong><span>{t("builder.openDraft")}</span></div>
                </div>
                <div className="test-card-meta">
                  <span>{t("builder.updated", { date: formatUpdated(test.updated_at, t("builder.recently")) })}</span>
                  {latest ? <span>{t("builder.latest", { number: latest.version_number })}</span> : <span>{t("builder.noVersions")}</span>}
                </div>
                <div className="test-card-actions">
                  <Link href={`/admin/tests/${test.id}`} className="btn btn-secondary">{t("common.open")}</Link>
                  {view === "active" && draft ? (
                    <Link href={builderEditPath(test.id, draft.id)} className="btn btn-primary">
                      {t("builder.continueDraft")} <ArrowIcon className="size-4" />
                    </Link>
                  ) : view === "active" && published ? (
                    <button type="button" disabled={pendingId !== null} onClick={() => void editPublished(test)} className="btn btn-primary">{t("common.edit")} <ArrowIcon className="size-4" /></button>
                  ) : view === "archived" ? (
                    <button type="button" disabled={pendingId !== null} aria-label={t("builder.restoreNamed", { title: test.title })} onClick={() => void restore(test)} className="btn btn-primary">
                      {t("common.restore")}
                    </button>
                  ) : null}
                  {view === "active" ? (
                    <button type="button" disabled={pendingId !== null} aria-label={`${destructiveLabel} ${test.title}`} onClick={() => setSelected(test)} className="btn btn-danger-ghost ml-auto">
                      {destructiveLabel}
                    </button>
                  ) : <button type="button" disabled={pendingId !== null} aria-label={t("builder.deleteNamed", { title: test.title })} onClick={() => setPermanentSelected(test)} className="btn btn-danger-ghost ml-auto">{t("common.deletePermanently")}</button>}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mt-5">
          <EmptyState
            icon={view === "archived" ? <ArchiveIcon className="size-6" /> : undefined}
            title={query ? t("builder.noMatching") : view === "active" ? t("builder.ready") : t("builder.archiveEmpty")}
            description={query ? t("builder.searchHelp") : view === "active" ? t("builder.firstTest") : t("builder.archiveHelp")}
          />
        </div>
      )}

      <ConfirmDialog
        open={selected !== null}
        title={selectedWillArchive ? t("builder.archiveTitle", { title: selected?.title ?? "" }) : t("builder.deleteTitle", { title: selected?.title ?? "" })}
        description={selectedWillArchive ? t("builder.archiveDescription") : t("common.cannotUndo")}
        confirmLabel={selectedWillArchive ? t("common.archive") : t("common.delete")}
        pending={pendingId !== null}
        onCancel={() => setSelected(null)}
        onConfirm={() => void removeSelected()}
      />
      <ConfirmDialog open={permanentSelected !== null} title={t("builder.permanentTitle", { title: permanentSelected?.title ?? "" })} description={t("builder.permanentDescription")} confirmLabel={t("common.deletePermanently")} pending={pendingId !== null} onCancel={() => setPermanentSelected(null)} onConfirm={() => void permanentlyRemove()} />
    </>
  );
}

function hasHistory(test: TestSummary): boolean {
  return test.versions.some((version) => version.status === "PUBLISHED" || version.status === "ARCHIVED");
}

function formatUpdated(value: string, recently: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return recently;
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}
