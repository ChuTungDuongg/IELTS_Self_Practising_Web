"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { builderEditPath } from "@/lib/routes";
import { AutosaveLink } from "./autosave-link";

export type BuilderWorkspace = "overview" | "reading" | "listening" | "writing";

type RowProps = { active: boolean; disabled?: boolean; href?: string; icon: React.ReactNode; label: string; status: string; tone: BuilderWorkspace | "writing" };

export function BuilderWorkspaceRow({ active, disabled, href, icon, label, status, tone }: RowProps) {
  const content = <>{icon}<span className="builder-row-label">{label}</span><small>{status}</small></>;
  const className = `builder-workspace-row builder-workspace-${tone}${active ? " builder-local-active" : ""}${disabled ? " builder-workspace-disabled" : ""}`;
  return href && !disabled ? <AutosaveLink href={href} aria-current={active ? "page" : undefined} className={className}>{content}</AutosaveLink> : <span aria-disabled="true" className={className}>{content}</span>;
}

export function BuilderWorkspaceNavigation({ testId, versionId, workspace, moduleTypes = [] }: { testId: string; versionId: string; workspace: BuilderWorkspace; moduleTypes?: Array<"READING" | "LISTENING" | "WRITING"> }) {
  const { t } = useTranslation();
  const base = builderEditPath(testId, versionId);
  const exists = (type: "READING" | "LISTENING" | "WRITING") => moduleTypes.includes(type);
  return (
    <aside className="builder-local-nav" aria-label={t("builder.sections")}>
      <p>{t("builder.structure")}</p>
      <BuilderWorkspaceRow tone="overview" active={workspace === "overview"} href={`${base}?workspace=overview`} icon={<BuilderIcon className="size-4" />} label={t("shell.overview")} status={t("builder.summary")} />
      <BuilderWorkspaceRow tone="reading" active={workspace === "reading"} href={`${base}?workspace=reading`} icon={<ReadingIcon className="size-4" />} label={t("common.reading")} status={exists("READING") ? t("builder.created") : t("builder.notCreated")} />
      <BuilderWorkspaceRow tone="listening" active={workspace === "listening"} href={`${base}?workspace=listening`} icon={<BuilderIcon className="size-4" />} label={t("common.listening")} status={exists("LISTENING") ? t("builder.created") : t("builder.notCreated")} />
      <BuilderWorkspaceRow tone="writing" active={workspace === "writing"} href={`${base}?workspace=writing`} icon={<BuilderIcon className="size-4" />} label={t("common.writing")} status={exists("WRITING") ? t("builder.created") : t("builder.notCreated")} />
    </aside>
  );
}
