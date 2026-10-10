"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

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
  const { t } = useTranslation();
  return <>
    {offline ? <p role="status" className="notice">{t("runner.offline")}</p> : null}
    {Object.values(conflicts).map((conflict) => <div key={conflict.id} role="alert" className="notice notice-error">
      <p><strong>{t("runner.recoveredConflict", { label: labelFor(conflict.id) })}</strong> {t("runner.recoveredDescription")}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary" onClick={() => onResolve(conflict.id, "saved")}>{t("runner.useSaved")}</button>
        <button type="button" className="btn btn-primary" onClick={() => onResolve(conflict.id, "recovered")}>{t("runner.restoreUnsaved")}</button>
      </div>
    </div>)}
  </>;
}
