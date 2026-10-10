"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ModuleBadge } from "@/components/ui/module-badge";
import { ArrowIcon } from "@/components/ui/icons";
import { StartAttempt } from "@/features/exam/start-attempt";
import { StartFullMock } from "@/features/exam/start-full-mock";
import { ContentSummary, publishedContentSummary } from "@/features/test-builder/content-summary";
import type { TestSummary, VersionDetail } from "@/lib/api/schema";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";

const moduleOrder = { READING: 0, LISTENING: 1, WRITING: 2 } as const;

export function LibraryContent({ items }: { items: Array<{ test: TestSummary; version: TestSummary["versions"][number]; detail: VersionDetail }> }): ReactElement {
  const { t } = useTranslation();
  return <>
    <PageHeading eyebrow={t("pages.library.practice")} title={t("pages.library.choose")} description={t("pages.library.chooseDescription")} />
    {items.length ? <div className="practice-grid">
      {items.map(({ test, version, detail }) => {
        const modules = [...detail.modules].sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);
        return <article key={version.id} className="practice-card practice-test-card">
          <div className="practice-card-accent" aria-hidden="true" />
          <div className="practice-card-content">
            <div className="practice-card-topline"><span className="practice-version">{t("common.versionNumber", { number: version.version_number })}</span><StatusBadge status={version.status} label={t(statusTranslationKeys[version.status])} /></div>
            <div className="practice-card-title"><p className="practice-module-kicker">{t("pages.library.complete")}</p><h2>{test.title}</h2><span>{test.description ?? t("pages.library.fallback")}</span></div>
            <div className="practice-module-chips" aria-label={t("pages.library.skillsLabel", { title: test.title })}>{modules.map((module) => <ModuleBadge key={module.id} module={module.module_type} label={t(moduleTranslationKeys[module.module_type])} />)}</div>
            <p className="practice-skill-count">{t("pages.library.skillsCount", { count: modules.length })}</p>
            <Link className="btn btn-primary practice-open-test" href={`/library/${version.id}`}>{t("pages.library.open")} <ArrowIcon className="size-4" /></Link>
          </div>
        </article>;
      })}
    </div> : <EmptyState title={t("pages.library.empty")} description={t("pages.library.emptyDescription")} />}
  </>;
}

export function LibraryVersionContent({ test, version }: { test: TestSummary; version: VersionDetail }): ReactElement {
  const { t } = useTranslation();
  const modules = [...version.modules].sort((left, right) => moduleOrder[left.module_type] - moduleOrder[right.module_type]);
  const missing = (["LISTENING", "READING", "WRITING"] as const).find((type) => !modules.some((item) => item.module_type === type));
  const missingDuration = modules.find((item) => !item.recommended_duration_seconds || item.recommended_duration_seconds <= 0);
  const readinessWarnings = modules.filter((item) => (item.module_type === "READING" || item.module_type === "LISTENING") && item.question_count !== 40).map((item) => t("pages.library.bandWarning", { skill: t(moduleTranslationKeys[item.module_type]), count: item.question_count }));

  return <>
    <Link href="/library" className="practice-back-link">← {t("pages.library.back")}</Link>
    <PageHeading eyebrow={t("pages.library.publishedVersion", { number: version.version_number })} title={test.title} description={test.description ?? t("pages.library.detailFallback")} />
    <StartFullMock versionId={version.id} warnings={readinessWarnings} unavailableReason={missing ? t("pages.library.missingModule", { skill: t(moduleTranslationKeys[missing]) }) : missingDuration ? t("pages.library.missingDuration", { skill: t(moduleTranslationKeys[missingDuration.module_type]) }) : undefined} />
    <h2 className="mt-8 mb-4">{t("pages.library.individual")}</h2><div className="practice-skill-grid">
      {modules.map((module) => <article key={module.id} className={`practice-card practice-card-${module.module_type.toLowerCase()}`}>
        <div className="practice-card-accent" aria-hidden="true" />
        <div className="practice-card-content">
          <div className="practice-card-topline"><ModuleBadge module={module.module_type} label={t(moduleTranslationKeys[module.module_type])} /></div>
          <div className="practice-card-title"><p className="practice-module-kicker">{t("pages.library.skillPractice", { skill: t(moduleTranslationKeys[module.module_type]) })}</p><h2>{module.title ?? t(moduleTranslationKeys[module.module_type])}</h2><span>{t("pages.library.continue")}</span></div>
          <dl className="practice-card-meta">
            <div><dt>{t("pages.library.version")}</dt><dd>{version.version_number}</dd></div>
            <div><dt>{module.module_type === "WRITING" ? t("common.tasks") : t("common.questions")}</dt><dd>{module.module_type === "WRITING" ? module.writing_task_count : module.question_count}</dd></div>
            <div><dt>{module.module_type === "LISTENING" ? t("common.sections") : module.module_type === "WRITING" ? t("common.suggestedTime") : t("common.passages")}</dt><dd>{module.module_type === "LISTENING" ? module.listening_part_count : module.module_type === "WRITING" ? t("common.minutesShort", { count: Math.round((module.recommended_duration_seconds ?? 3600) / 60) }) : module.passage_count}</dd></div>
          </dl>
          <ContentSummary units={publishedContentSummary(module)} />
          <StartAttempt versionId={version.id} module={module.module_type} />
        </div>
      </article>)}
    </div>
  </>;
}
