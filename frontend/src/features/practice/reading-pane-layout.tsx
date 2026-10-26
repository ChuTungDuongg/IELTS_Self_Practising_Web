import type { ReactNode } from "react";
import type { AttemptPresentationMode } from "@/features/exam/attempt-presentation";
import { PracticeTools } from "./practice-tools";
import { ReadingSplitPane } from "./reading-split-pane";
import styles from "./practice-runner.module.css";

export function ReadingPaneLayout({ id, presentation, children }: { id: string; presentation: AttemptPresentationMode; children: [ReactNode, ReactNode] }) {
  if (presentation === "EXAM") return <div id={id} className="grid min-h-0 flex-1 lg:grid-cols-2">{children}</div>;
  return <div className={styles.workspace}><PracticeTools /><ReadingSplitPane id={id}>{children}</ReadingSplitPane></div>;
}
