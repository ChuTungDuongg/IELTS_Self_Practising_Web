import Link from "next/link";
import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { builderEditPath } from "@/lib/routes";

export type BuilderWorkspace = "overview" | "reading" | "listening" | "writing";

type RowProps = { active: boolean; disabled?: boolean; href?: string; icon: React.ReactNode; label: string; status: string; tone: BuilderWorkspace | "writing" };

export function BuilderWorkspaceRow({ active, disabled, href, icon, label, status, tone }: RowProps) {
  const content = <>{icon}<span className="builder-row-label">{label}</span><small>{status}</small></>;
  const className = `builder-workspace-row builder-workspace-${tone}${active ? " builder-local-active" : ""}${disabled ? " builder-workspace-disabled" : ""}`;
  return href && !disabled ? <Link href={href} aria-current={active ? "page" : undefined} className={className}>{content}</Link> : <span aria-disabled="true" className={className}>{content}</span>;
}

export function BuilderWorkspaceNavigation({ testId, versionId, workspace, moduleTypes = [] }: { testId: string; versionId: string; workspace: BuilderWorkspace; moduleTypes?: Array<"READING" | "LISTENING" | "WRITING"> }) {
  const base = builderEditPath(testId, versionId);
  const exists = (type: "READING" | "LISTENING" | "WRITING") => moduleTypes.includes(type);
  return (
    <aside className="builder-local-nav" aria-label="Builder sections">
      <p>Test structure</p>
      <BuilderWorkspaceRow tone="overview" active={workspace === "overview"} href={`${base}?workspace=overview`} icon={<BuilderIcon className="size-4" />} label="Overview" status="Summary" />
      <BuilderWorkspaceRow tone="reading" active={workspace === "reading"} href={`${base}?workspace=reading`} icon={<ReadingIcon className="size-4" />} label="Reading" status={exists("READING") ? "Created" : "Not created"} />
      <BuilderWorkspaceRow tone="listening" active={workspace === "listening"} href={`${base}?workspace=listening`} icon={<BuilderIcon className="size-4" />} label="Listening" status={exists("LISTENING") ? "Created" : "Not created"} />
      <BuilderWorkspaceRow tone="writing" active={workspace === "writing"} href={`${base}?workspace=writing`} icon={<BuilderIcon className="size-4" />} label="Writing" status={exists("WRITING") ? "Created" : "Not created"} />
    </aside>
  );
}
