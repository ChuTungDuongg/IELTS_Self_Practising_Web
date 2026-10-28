"use client";

import { useMemo, useState, type ReactElement } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/ui/status-badge";
import { PageHeading } from "@/components/ui/page-heading";
import { EmptyState } from "@/components/ui/empty-state";
import { DataLoadNotice } from "@/components/ui/data-load-notice";
import { ModuleBadge } from "@/components/ui/module-badge";
import { AnalyticsIcon, ArrowIcon, BuilderIcon, SearchIcon } from "@/components/ui/icons";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFullMock } from "@/features/exam/start-full-mock";
import { ContentSummary, publishedContentSummary } from "@/features/test-builder/content-summary";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys } from "@/lib/i18n/translations";
import { selectedPublishedVersion } from "@/lib/published-version";
import { fullMockEligibility } from "./full-mock-eligibility";
import "./practice-library.css";

const moduleOrder = { READING: 0, LISTENING: 1, WRITING: 2, SPEAKING: 3 } as const;
type RuntimeModule = VersionDetail["modules"][number] & { module_type: keyof typeof moduleOrder };
function runtimeModules(modules: VersionDetail["modules"]) {
  return ([...modules] as RuntimeModule[])
    .sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);
}

export function TestAttribution({ test, compact = false }: { test: TestSummary; compact?: boolean }) {
  const { t } = useTranslation();
  const label = test.origin === "TEACHER" ? t("library.community", { name: test.owner_display_name ?? t("library.contributor") }) : t("library.official");
  return compact ? <span className="practice-detail-origin">{label}</span> : <p className="practice-module-kicker">{label}</p>;
}

type LibraryItem = { test: TestSummary; version: TestSummary["versions"][number]; detail: VersionDetail };
type SkillFilter = "ALL" | keyof typeof moduleOrder | "FULL_MOCK";
type Sort = "recent" | "oldest" | "az" | "za";
const skills = ["READING", "LISTENING", "WRITING", "SPEAKING"] as const;

export function LibraryContent({ items, loadFailed = false }: { items: LibraryItem[]; loadFailed?: boolean }): ReactElement {
  const { t } = useTranslation();
  const { locale } = useLocale();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SkillFilter>("ALL");
  const [sort, setSort] = useState<Sort>("recent");

  const selected = useMemo(() => {
    const grouped = new Map<string, LibraryItem[]>();
    for (const item of items) {
      if (item.test.archived_at || item.detail.status !== "PUBLISHED" || item.version.status !== "PUBLISHED" || item.detail.id !== item.version.id || item.detail.test_id !== item.test.id) continue;
      const group = grouped.get(item.test.id) ?? [];
      group.push(item);
      grouped.set(item.test.id, group);
    }
    return [...grouped.values()].flatMap(group => {
      const version = selectedPublishedVersion(group.map(item => item.version));
      const match = group.find(item => item.version.id === version?.id);
      return match ? [match] : [];
    });
  }, [items]);

  const visible = useMemo(() => {
    const normalized = query.trim().normalize("NFC").toLocaleLowerCase(locale);
    const collator = new Intl.Collator(locale, { sensitivity: "base", numeric: true });
    return selected.filter(({ test, detail }) => {
      if (filter === "FULL_MOCK" && !fullMockEligibility(detail.modules).available) return false;
      if (filter !== "ALL" && filter !== "FULL_MOCK" && !detail.modules.some(module => module.module_type === filter)) return false;
      return !normalized || [test.title, test.description, test.source_label].some(value => value?.normalize("NFC").toLocaleLowerCase(locale).includes(normalized));
    }).sort((left, right) => {
      if (sort === "az" || sort === "za") return collator.compare(left.test.title, right.test.title) * (sort === "az" ? 1 : -1) || left.test.id.localeCompare(right.test.id);
      const diff = (Date.parse(left.test.updated_at) || 0) - (Date.parse(right.test.updated_at) || 0);
      return diff * (sort === "recent" ? -1 : 1) || left.test.id.localeCompare(right.test.id);
    });
  }, [selected, query, filter, sort, locale]);

  const counts = useMemo(() => ({
    fullMock: selected.filter(({ detail }) => fullMockEligibility(detail.modules).available).length,
    skills: Object.fromEntries(skills.map(skill => [skill, selected.filter(({ detail }) => detail.modules.some(module => module.module_type === skill)).length])) as Record<typeof skills[number], number>,
  }), [selected]);

  const hasFilters = !!query || filter !== "ALL" || sort !== "recent";
  function resetFilters() { setQuery(""); setFilter("ALL"); setSort("recent"); }
  return <section className="practice-library">
    <PageHeading eyebrow={t("pages.practice")} title={t("catalog.title")} description={t("catalog.description")} />
    {loadFailed && <DataLoadNotice message={selected.length ? "ui.partialLoad" : "catalog.loadFailed"} />}
    {selected.length > 0 && <div className="practice-library-layout">
      <div className="practice-library-toolbar">
        <div className="practice-library-search"><SearchIcon /><input aria-label={t("catalog.search")} placeholder={t("catalog.searchPlaceholder")} value={query} onChange={event => setQuery(event.target.value)} />{query && <button type="button" aria-label={t("common.clearSearch")} onClick={() => setQuery("")}>×</button>}</div>
        <label className="practice-library-sort"><span className="sr-only">{t("catalog.sort")}</span><select value={sort} onChange={event => setSort(event.target.value as Sort)}><option value="recent">{t("catalog.recent")}</option><option value="oldest">{t("catalog.oldest")}</option><option value="az">{t("catalog.az")}</option><option value="za">{t("catalog.za")}</option></select></label>
      </div>
      <aside className="practice-library-sidebar">
        <section className="practice-library-panel">
          <h2>{t("catalog.quickSkills")}</h2>
          <div className="practice-library-filters" role="group" aria-label={t("catalog.filter")}>
            <button type="button" aria-pressed={filter === "ALL"} onClick={() => setFilter("ALL")}>{t("catalog.all")}</button>
            {skills.map(skill => <button key={skill} type="button" aria-pressed={filter === skill} onClick={() => setFilter(skill)}>{t(moduleTranslationKeys[skill])}</button>)}
            <button type="button" aria-pressed={filter === "FULL_MOCK"} onClick={() => setFilter("FULL_MOCK")}>{t("practice.fullMock")}</button>
          </div>
        </section>
        <section className="practice-library-panel" aria-labelledby="practice-library-statistics">
          <h2 id="practice-library-statistics"><AnalyticsIcon />{t("catalog.statistics")}</h2>
          <p className="practice-library-statistics-hint">{t("catalog.statsHint")}</p>
          <dl className="practice-library-statistics">
            <div><dt>{t("catalog.availableTests")}</dt><dd>{selected.length}</dd></div>
            <div><dt>{t("catalog.fullMockCount")}</dt><dd>{counts.fullMock}</dd></div>
            {skills.map(skill => <div key={skill}><dt>{t(moduleTranslationKeys[skill])}</dt><dd>{counts.skills[skill]}</dd></div>)}
          </dl>
          {loadFailed && <p className="practice-library-partial-counts">{t("catalog.partialCounts")}</p>}
        </section>
      </aside>
      <div className="practice-library-content">
        <p className="practice-library-results" role="status" aria-live="polite">{t("catalog.results", { count: visible.length })}</p>
        {visible.length ? <div className="practice-library-grid">
          {visible.map(({ test, version, detail }) => {
            const modules = runtimeModules(detail.modules);
            const uniqueSkills = [...new Set(modules.map(module => module.module_type))];
            return <article key={test.id} className="practice-library-card">
              <div className="practice-library-card-body">
                <div className="practice-library-icon" aria-hidden="true"><BuilderIcon /></div>
                <div className="practice-library-card-info">
                  <div className="practice-library-card-top"><TestAttribution test={test} compact /><StatusBadge status="PUBLISHED" label={t("common.published")} /></div>
                  <h2>{test.title}</h2><p className="practice-library-card-description">{test.description ?? t("pages.library.fallback")}</p>
                  <div className="practice-library-chips" aria-label={t("pages.library.skillsLabel", { title: test.title })}>{uniqueSkills.map(skill => <ModuleBadge key={skill} module={skill} label={t(moduleTranslationKeys[skill])} />)}</div>
                </div>
              </div>
              <p className="practice-library-skill-count">{t("pages.library.skillsCount", { count: uniqueSkills.length })}</p>
              <Link className="btn btn-primary practice-library-open" href={`/library/${encodeURIComponent(version.id)}`}>{t("pages.library.open")} <ArrowIcon className="size-4" /></Link>
            </article>;
          })}
        </div> : <div className="practice-library-empty"><h2>{t("catalog.noResults")}</h2><p>{t("catalog.noResultsHelp")}</p><button type="button" className="btn btn-secondary" onClick={resetFilters}>{t("catalog.reset")}</button></div>}
        {filter === "FULL_MOCK" && <p className="practice-library-full-note">{t("catalog.fullMockNote")}</p>}
        {hasFilters && visible.length > 0 && <button type="button" className="practice-library-reset" onClick={resetFilters}>{t("catalog.reset")}</button>}
      </div>
    </div>}
    {!selected.length && !loadFailed && <EmptyState title={t("pages.library.empty")} description={t("catalog.emptyDescription")} />}
  </section>;
}

export function LibraryVersionContent({ test, version }: { test: TestSummary; version: VersionDetail }): ReactElement {
  const { t } = useTranslation();
  const modules = runtimeModules(version.modules);
  const { missing, missingDuration } = fullMockEligibility(modules);
  const readinessWarnings = modules.filter((item) => (item.module_type === "READING" || item.module_type === "LISTENING") && item.question_count !== 40).map((item) => t("pages.library.bandWarning", { skill: t(moduleTranslationKeys[item.module_type]), count: item.question_count }));

  return <>
    <div className="practice-detail-header">
      <Link href="/library" className="practice-back-link practice-detail-back-link">← {t("pages.library.back")}</Link>
      <div className="practice-detail-title-row">
        <h1>{test.title}</h1>
        <div className="practice-detail-meta">
          <TestAttribution test={test} compact />
          <StatusBadge status={version.status} label={t("common.published")} />
        </div>
      </div>
      {test.description ? <p className="practice-detail-description">{test.description}</p> : null}
    </div>
    <StartFullMock versionId={version.id} preview={{ title: test.title }} warnings={readinessWarnings} unavailableReason={missing ? t("pages.library.missingModule", { skill: t(moduleTranslationKeys[missing]) }) : missingDuration ? t("pages.library.missingDuration", { skill: t(moduleTranslationKeys[missingDuration.module_type]) }) : undefined} />
    <h2 className="practice-detail-individual-heading">{t("pages.library.individual")}</h2><div className="practice-skill-grid">
      {modules.map((module) => <article key={module.id} className={`practice-card practice-card-${module.module_type.toLowerCase()}`}>
        <div className="practice-card-accent" aria-hidden="true" />
        <div className="practice-card-content">
          <div className="practice-card-topline"><ModuleBadge module={module.module_type} label={t(moduleTranslationKeys[module.module_type])} /></div>
          <div className="practice-card-title"><p className="practice-module-kicker">{t("pages.library.skillPractice", { skill: t(moduleTranslationKeys[module.module_type]) })}</p><h2>{module.title ?? t(moduleTranslationKeys[module.module_type])}</h2><span>{t("pages.library.continue")}</span></div>
          <dl className="practice-card-meta">
            <div><dt>{module.module_type === "WRITING" ? t("common.tasks") : t("common.questions")}</dt><dd>{module.module_type === "WRITING" ? module.writing_task_count : module.question_count}</dd></div>
            <div><dt>{module.module_type === "LISTENING" ? t("common.sections") : module.module_type === "WRITING" ? t("common.suggestedTime") : module.module_type === "SPEAKING" ? t("common.parts") : t("common.passages")}</dt><dd>{module.module_type === "LISTENING" ? module.listening_part_count : module.module_type === "WRITING" ? (module.recommended_duration_seconds ?? 0) > 0 ? t("common.minutesShort", { count: Math.round((module.recommended_duration_seconds ?? 0) / 60) }) : t("builder.notSet") : module.module_type === "SPEAKING" ? module.speaking_parts?.length ?? 0 : module.passage_count}</dd></div>
          </dl>
          <ContentSummary units={publishedContentSummary(module)} />
          <StartAttempt versionId={version.id} module={module.module_type} preview={{ title: test.title, unitTitle: module.reading_passages?.[0]?.title ?? module.listening_sections?.[0]?.title, questionTypes: (module.reading_passages?.[0]?.question_groups ?? module.listening_sections?.[0]?.question_groups)?.map(group => group.question_type), questionCount: module.question_count }} />
        </div>
      </article>)}
    </div>
  </>;
}
