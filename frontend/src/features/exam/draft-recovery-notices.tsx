"use client";

import type { RecoveryConflict } from "./exam-draft-recovery";

export function DraftRecoveryNotices<Value>({
  offline,
  conflicts,
  labelFor,
  onResolve,
}: {
  offline: boolean;
  conflicts: Record<string, RecoveryConflict<Value>>;
  labelFor: (id: string) => string;
  onResolve: (id: string, choice: "saved" | "recovered") => void;
}) {
  return <>
    {offline ? <p role="status" className="notice">Offline — changes are kept in this tab.</p> : null}
    {Object.values(conflicts).map((conflict) => <div key={conflict.id} role="alert" className="notice notice-error">
      <p><strong>Recovered draft conflict for {labelFor(conflict.id)}.</strong> We recovered an unsaved response from this tab, but the saved response has changed since then.</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary" onClick={() => onResolve(conflict.id, "saved")}>Use saved response</button>
        <button type="button" className="btn btn-primary" onClick={() => onResolve(conflict.id, "recovered")}>Restore my unsaved response</button>
      </div>
    </div>)}
  </>;
}
