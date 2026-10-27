"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { ActionMenu } from "../lms/action-menu";
import { useContentTranslation } from "./content-messages";

const query = "(max-width: 640px)";
function subscribe(onChange: () => void) {
  const media = window.matchMedia?.(query);
  media?.addEventListener("change", onChange);
  return () => media?.removeEventListener("change", onChange);
}
const snapshot = () => window.matchMedia?.(query).matches ?? false;
const serverSnapshot = () => false;

/** Only one set of controls is mounted; desktop and mobile share the same operations. */
export function ArchiveActionLayout({ children, secondary }: { children: ReactNode; secondary?: ReactNode }) {
  const compact = useSyncExternalStore(subscribe, snapshot, serverSnapshot), { ct } = useContentTranslation();
  return <div className="classroom-archive-action-layout" data-compact={compact}>
    {compact ? <ActionMenu label={ct("itemActions")} iconOnly>{children}{secondary}</ActionMenu> : <>{children}{secondary ? <ActionMenu label={ct("itemActions")} iconOnly>{secondary}</ActionMenu> : null}</>}
  </div>;
}
