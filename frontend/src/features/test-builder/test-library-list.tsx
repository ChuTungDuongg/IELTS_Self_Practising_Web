"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PageHeading } from "@/components/ui/page-heading";
import { CoverThumbnail } from "@/features/test-builder/test-cover";
import { BuilderIcon, PlusIcon, SearchIcon } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";
import type { TestSummary } from "@/lib/api/schema";
import { cloneVersion, deleteTest, permanentlyDeleteTest, restoreTest } from "@/lib/api/tests";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";
import { selectedPublishedVersion } from "@/lib/published-version";
import { builderEditPath, type BuilderNamespace } from "@/lib/routes";
import "./authoring-library.css";

type Message = { kind: "success" | "error"; text: string | { message: TranslationKey; params?: TranslationParams } };
type Sort = "recent" | "oldest" | "az" | "za";

function draftOf(test: TestSummary) {
  return test.versions.filter(v => v.status === "DRAFT").sort((a, b) => b.version_number - a.version_number || a.id.localeCompare(b.id))[0];
}
function hasHistory(test: TestSummary) {
  return test.versions.some(v => v.status === "PUBLISHED" || v.status === "ARCHIVED");
}

export function AuthoringLibrary({ namespace, activeTests: initialActive, archivedTests: initialArchived, loadError = false }: {
  namespace: BuilderNamespace; activeTests: TestSummary[]; archivedTests: TestSummary[]; loadError?: boolean;
}) {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const router = useRouter();
  const [activeTests, setActiveTests] = useState(initialActive);
  const [archivedTests, setArchivedTests] = useState(initialArchived);
  const [view, setView] = useState<"active" | "archived">("active");
  const [filter, setFilter] = useState<"all" | "draft" | "published">("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("recent");
  const [selected, setSelected] = useState<TestSummary | null>(null);
  const [permanentSelected, setPermanentSelected] = useState<TestSummary | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const pending = useRef(false);
  const [message, setMessage] = useState<Message | null>(null);
  const willArchive = selected ? hasHistory(selected) : false;
  const messageText = message ? typeof message.text === "string" ? message.text : t(message.text.message, message.text.params) : null;

  async function run(target: TestSummary, action: () => Promise<void>, fallback: TranslationKey) {
    if (pending.current) return;
    pending.current = true; setPendingId(target.id); setMessage(null);
    try { await action(); }
    catch (error) { setMessage({ kind: "error", text: error instanceof ApiError ? error.message : { message: fallback } }); }
    finally { pending.current = false; setPendingId(null); }
  }
  function removeSelected() {
    if (!selected) return;
    const target = selected;
    void run(target, async () => {
      const result = await deleteTest(target.id);
      setActiveTests(current => current.filter(item => item.id !== target.id));
      if (result.action === "ARCHIVED") setArchivedTests(current => [{ ...target, archived_at: new Date().toISOString() }, ...current]);
      setSelected(null);
      setMessage({ kind: "success", text: { message: result.action === "ARCHIVED" ? "builder.archivedNamed" : "builder.deletedNamed", params: { title: target.title } } });
    }, "builder.removeFailed");
  }
  function restore(target: TestSummary) {
    void run(target, async () => {
      const restored = await restoreTest(target.id);
      setArchivedTests(current => current.filter(item => item.id !== target.id));
      setActiveTests(current => [{ ...target, ...restored, owner_display_name: restored.owner_display_name ?? target.owner_display_name }, ...current]);
      setMessage({ kind: "success", text: { message: "builder.restoredNamed", params: { title: target.title } } });
    }, "builder.restoreFailed");
  }
  function editPublished(target: TestSummary) {
    const published = selectedPublishedVersion(target.versions);
    if (!published) return;
    void run(target, async () => {
      const draft = await cloneVersion(target.id, published.id);
      router.push(builderEditPath(target.id, draft.id, namespace));
    }, "builder.openDraftFailed");
  }
  function permanentlyRemove() {
    if (!permanentSelected) return;
    const target = permanentSelected;
    void run(target, async () => {
      await permanentlyDeleteTest(target.id);
      setArchivedTests(current => current.filter(item => item.id !== target.id));
      setPermanentSelected(null);
      setMessage({ kind: "success", text: { message: "builder.permanentlyDeletedNamed", params: { title: target.title } } });
    }, "builder.permanentDeleteFailed");
  }

  const counts = useMemo(() => ({ drafts: activeTests.filter(test => !!draftOf(test)).length, published: activeTests.filter(test => !!selectedPublishedVersion(test.versions)).length }), [activeTests]);
  const filteredTests = useMemo(() => {
    const normalized = query.trim().normalize("NFC").toLocaleLowerCase(locale);
    const collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
    return (view === "active" ? activeTests : archivedTests).filter(test => {
      if (view === "active" && filter === "draft" && !draftOf(test)) return false;
      if (view === "active" && filter === "published" && !selectedPublishedVersion(test.versions)) return false;
      return !normalized || [test.title, test.description, test.source_label].some(value => value?.normalize("NFC").toLocaleLowerCase(locale).includes(normalized));
    }).sort((a, b) => {
      if (sort === "az" || sort === "za") return collator.compare(a.title, b.title) * (sort === "az" ? 1 : -1) || a.id.localeCompare(b.id);
      const delta = (Date.parse(a.updated_at) || 0) - (Date.parse(b.updated_at) || 0);
      return delta * (sort === "recent" ? -1 : 1) || a.id.localeCompare(b.id);
    });
  }, [activeTests, archivedTests, view, filter, query, sort, locale]);
  function date(value: string) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? t("builder.recently") : new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(parsed);
  }
  return <section className="authoring-library">
    <PageHeading
      eyebrow={t("builder.workspace")}
      title={t("authoring.title")}
      description={<>{t("authoring.subtitle")}{namespace === "teacher" && <><br />{t("moderation.requireReview")}</>}</>}
      action={<div className="authoring-header-actions">{namespace === "admin" && <Link href="/transfer" className="btn btn-secondary">{t("authoring.transfer")}</Link>}<Link href={`/${namespace}/tests/new`} className="btn btn-primary"><PlusIcon className="size-4" /> {t("builder.newTest")}</Link></div>}
    />
    {loadError ? <div className="authoring-empty" role="alert"><p>{t("authoring.loadError")}</p><a href={`/${namespace}/tests`} className="btn btn-secondary">{t("authoring.retry")}</a></div> : <>
      <div className="authoring-metrics" aria-label={t("authoring.title")}>
        {([["authoring.total", activeTests.length], ["authoring.drafts", counts.drafts], ["authoring.published", counts.published], ["authoring.archived", archivedTests.length]] as const).map(([label, count], index) => <div className={`authoring-metric authoring-metric-${index}`} key={label}><span className="authoring-metric-icon" aria-hidden="true"><BuilderIcon /></span><div><strong>{count}</strong><span>{t(label)}</span></div></div>)}
      </div>
      <p className="authoring-metric-note">{t("authoring.overlap")}</p>
      <div className="authoring-toolbar library-toolbar">
        <div className="authoring-tabs" role="tablist" aria-label={t("builder.testStatus")} onKeyDown={event => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") return;
          event.preventDefault();
          const next = event.key === "Home" ? "active" : event.key === "End" ? "archived" : view === "active" ? "archived" : "active";
          setView(next);
          event.currentTarget.querySelectorAll<HTMLButtonElement>("[role=tab]")[next === "active" ? 0 : 1]?.focus();
        }}>
          <button role="tab" tabIndex={view === "active" ? 0 : -1} aria-selected={view === "active"} onClick={() => setView("active")}>{t("builder.activeTab")} ({activeTests.length})</button>
          <button role="tab" tabIndex={view === "archived" ? 0 : -1} aria-selected={view === "archived"} onClick={() => setView("archived")}>{t("common.archived")} ({archivedTests.length})</button>
        </div>
        {view === "active" && <label className="authoring-select"><span className="sr-only">{t("builder.testStatus")}</span><select value={filter} onChange={event => setFilter(event.target.value as typeof filter)}><option value="all">{t("authoring.all")}</option><option value="draft">{t("authoring.draftFilter")}</option><option value="published">{t("authoring.publishedFilter")}</option></select></label>}
        <div className="authoring-search"><SearchIcon /><input aria-label={t("builder.search")} value={query} onChange={event => setQuery(event.target.value)} placeholder={t("builder.searchPlaceholder")} />{query && <button type="button" aria-label={t("common.clearSearch")} onClick={() => setQuery("")}>×</button>}</div>
        <label className="authoring-select"><span className="sr-only">{t("authoring.sort")}</span><select value={sort} onChange={event => setSort(event.target.value as Sort)}><option value="recent">{t("authoring.recent")}</option><option value="oldest">{t("authoring.oldest")}</option><option value="az">{t("authoring.az")}</option><option value="za">{t("authoring.za")}</option></select></label>
      </div>
      {message && !selected && !permanentSelected && <p role={message.kind === "error" ? "alert" : "status"} className={`notice ${message.kind === "error" ? "notice-error" : "notice-success"}`}>{messageText}</p>}
      <p className="authoring-result-count">{t("authoring.results", { count: filteredTests.length })}</p>
      {filteredTests.length ? <div className="authoring-rows">{filteredTests.map(test => {
        const draft = draftOf(test), published = selectedPublishedVersion(test.versions);
        // Teacher-authored tests remain in their moderation workflow, even when inspected by an admin.
        const canEdit = namespace === "teacher" || test.origin !== "TEACHER";
        const teacherVersion = draft ?? published ?? [...test.versions].sort((a, b) => b.version_number - a.version_number)[0];
        const details = namespace === "admin" ? `/admin/tests/${encodeURIComponent(test.id)}` : view === "active" && !draft && teacherVersion ? builderEditPath(test.id, teacherVersion.id, "teacher") : null;
        const destructive = hasHistory(test) ? t("common.archive") : t("common.delete");
        return <article className="authoring-row" key={test.id}>
          <CoverThumbnail cover={test.cover_image} title={test.title} className="authoring-row-icon" />
          <div className="authoring-row-content"><h2>{test.title}</h2>{test.description && <p className="authoring-description">{test.description}</p>}
            <div className="authoring-statuses">{view === "archived" ? <span className="authoring-status archived">{t("common.archived")}</span> : <>{published && <span className="authoring-status published">{t("common.published")}</span>}{draft && <span className="authoring-status draft">{t(published ? "authoring.draftChanges" : "common.draft")}</span>}{!draft && !published && <span className="authoring-status">{t("authoring.noVersions")}</span>}</>}</div>
            <div className="authoring-meta"><span>{t("builder.updated", { date: date(test.updated_at) })}</span>{test.source_label && <span>{t("authoring.source", { source: test.source_label })}</span>}{namespace === "admin" && test.origin && <span>{test.origin === "TEACHER" ? test.owner_display_name ? t("authoring.owner", { name: test.owner_display_name }) : t("authoring.teacherOrigin") : t("authoring.adminOrigin")}</span>}</div>
          </div>
          <div className="authoring-row-actions">
            {view === "archived" ? <button className="btn btn-primary" disabled={pendingId !== null} aria-label={t("builder.restoreNamed", { title: test.title })} onClick={() => restore(test)}>{t(pendingId === test.id ? "common.working" : "common.restore")}</button> : view === "active" && canEdit && draft ? <Link className="btn btn-primary" href={builderEditPath(test.id, draft.id, namespace)}>{t(namespace === "teacher" ? "authoring.teacherDraft" : "builder.continueDraft")}</Link> : view === "active" && canEdit && published ? <button className="btn btn-primary" disabled={pendingId !== null} onClick={() => editPublished(test)}>{t(pendingId === test.id ? "common.working" : "authoring.editTest")}</button> : null}
            {details && <Link href={details} className="btn btn-secondary">{t("authoring.details")}</Link>}
            {(view === "active" || namespace === "admin") && <details className="authoring-menu"><summary className="btn btn-secondary" aria-label={t("authoring.more", { title: test.title })}>⋯</summary><div className="authoring-menu-popover">{view === "active" ? <button type="button" disabled={pendingId !== null} aria-label={`${destructive} ${test.title}`} onClick={() => { setMessage(null); setSelected(test); }}>{destructive}</button> : <button type="button" disabled={pendingId !== null} aria-label={t("builder.deleteNamed", { title: test.title })} onClick={() => { setMessage(null); setPermanentSelected(test); }}>{t("common.deletePermanently")}</button>}</div></details>}
          </div>
        </article>;
      })}</div> : <div className="authoring-empty"><BuilderIcon /><h2>{query || (view === "active" && filter !== "all") ? t("builder.noMatching") : view === "active" ? t("builder.ready") : t("builder.archiveEmpty")}</h2><p>{query || (view === "active" && filter !== "all") ? t("authoring.emptyFiltered") : view === "active" ? t("builder.firstTest") : t("builder.archiveHelp")}</p>{query || filter !== "all" ? <button className="btn btn-secondary" onClick={() => { setQuery(""); setFilter("all"); }}>{t("authoring.clearFilters")}</button> : view === "active" && <Link className="btn btn-primary" href={`/${namespace}/tests/new`}>{t("builder.newTest")}</Link>}</div>}
    </>}
    <ConfirmDialog open={selected !== null} title={willArchive ? t("builder.archiveTitle", { title: selected?.title ?? "" }) : t("builder.deleteTitle", { title: selected?.title ?? "" })} description={willArchive ? t("builder.archiveDescription") : t("authoring.deleteDescription")} confirmLabel={willArchive ? t("common.archive") : t("common.delete")} pending={pendingId !== null} errorMessage={message?.kind === "error" ? messageText ?? undefined : undefined} onCancel={() => { setSelected(null); setMessage(null); }} onConfirm={removeSelected} />
    <ConfirmDialog open={permanentSelected !== null} title={t("builder.permanentTitle", { title: permanentSelected?.title ?? "" })} description={t("builder.permanentDescription")} confirmLabel={t("common.deletePermanently")} pending={pendingId !== null} errorMessage={message?.kind === "error" ? messageText ?? undefined : undefined} onCancel={() => { setPermanentSelected(null); setMessage(null); }} onConfirm={permanentlyRemove} />
  </section>;
}
export function TestLibraryList({ activeTests, archivedTests, loadError }: { activeTests: TestSummary[]; archivedTests: TestSummary[]; loadError?: boolean }) {
  return <AuthoringLibrary namespace="admin" activeTests={activeTests} archivedTests={archivedTests} loadError={loadError} />;
}
