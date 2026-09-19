import Link from "next/link";
import { BuilderIcon, ReadingIcon } from "@/components/ui/icons";
import { builderEditPath } from "@/lib/routes";

export type BuilderWorkspace = "overview" | "reading" | "listening";

export function BuilderWorkspaceNavigation({ testId, versionId, workspace }: { testId: string; versionId: string; workspace: BuilderWorkspace }) {
  const base = builderEditPath(testId, versionId);
  const item = (target: BuilderWorkspace, label: string, icon: React.ReactNode) => (
    <Link href={`${base}?workspace=${target}`} aria-current={workspace === target ? "page" : undefined} className={workspace === target ? "builder-local-active" : undefined}>
      {icon}{label}
    </Link>
  );
  return (
    <aside className="builder-local-nav" aria-label="Builder sections">
      <p>Test structure</p>
      {item("overview", "Overview", <BuilderIcon className="size-4" />)}
      {item("reading", "Reading", <ReadingIcon className="size-4" />)}
      {item("listening", "Listening", <span className="module-listening-dot" />)}
      <span><span className="module-writing-dot" /> Writing <small>Not created</small></span>
    </aside>
  );
}
