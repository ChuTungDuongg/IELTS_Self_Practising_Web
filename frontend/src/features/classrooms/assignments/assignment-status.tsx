"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useAssignmentsText } from "./messages";

export function AssignmentStatus({ archived, availableFrom }: { archived: boolean; availableFrom?: string | null }) {
  const { at } = useAssignmentsText();
  const snapshot = useCallback(() => !archived && Date.parse(availableFrom ?? "") > Date.now(), [archived, availableFrom]);
  const subscribe = useCallback((notify: () => void) => {
    let timer: number | undefined;
    function update() {
      window.clearTimeout(timer);
      notify();
      const remaining = Date.parse(availableFrom ?? "") - Date.now();
      if (!archived && remaining > 0) timer = window.setTimeout(update, Math.min(remaining + 1, 2_147_483_647));
    }
    update();
    window.addEventListener("focus", update);
    return () => { window.clearTimeout(timer); window.removeEventListener("focus", update); };
  }, [archived, availableFrom]);
  // This is a display badge; FastAPI remains authoritative for start eligibility.
  const scheduled = useSyncExternalStore(subscribe, snapshot, () => false);
  return <span className="assignments-status" data-status={archived ? "ARCHIVED" : scheduled ? "SCHEDULED" : "ACTIVE"}>{at(archived ? "archive" : scheduled ? "scheduled" : "open")}</span>;
}
