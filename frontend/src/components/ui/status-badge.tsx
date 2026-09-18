const styles: Record<string, string> = {
  DRAFT: "bg-amber-50 text-amber-800 ring-amber-200",
  PUBLISHED: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  ARCHIVED: "bg-slate-100 text-slate-700 ring-slate-200",
  IN_PROGRESS: "bg-blue-50 text-blue-800 ring-blue-200",
  SUBMITTED: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  AUTO_SUBMITTED: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  INTERRUPTED: "bg-amber-50 text-amber-800 ring-amber-200",
  ABANDONED: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${styles[status] ?? styles.ARCHIVED}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}
