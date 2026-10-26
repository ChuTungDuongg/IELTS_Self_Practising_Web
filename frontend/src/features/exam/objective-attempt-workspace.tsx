import type { ReactNode } from "react";
import { GlobalHeader } from "@/components/ui/global-header";
import styles from "./objective-attempt-workspace.module.css";

export function ObjectiveAttemptWorkspace({ attemptId, children }: { attemptId: string; children: ReactNode }) {
  return <div className={`app-shell ${styles.workspace}`}>
    <GlobalHeader pathname={`/attempt/${attemptId}`} />
    <div className={styles.runnerSlot}>{children}</div>
  </div>;
}
