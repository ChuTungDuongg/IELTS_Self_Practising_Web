import type { ReactNode } from "react";
import type { AttemptPresentationMode } from "@/features/exam/attempt-presentation";
import styles from "./practice-runner.module.css";

export function PracticeBottomNavigation({ presentation, children }: { presentation: AttemptPresentationMode; children: ReactNode }) {
  return presentation === "PRACTICE" ? <div className={styles.bottomNavigation} data-practice-bottom-navigation>{children}</div> : children;
}
