const styles: Record<string, string> = {
  DRAFT: "status-draft",
  PUBLISHED: "status-published",
  ARCHIVED: "status-archived",
  IN_PROGRESS: "status-progress",
  SUBMITTED: "status-published",
  AUTO_SUBMITTED: "status-published",
  INTERRUPTED: "status-draft",
  ABANDONED: "status-archived",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`status-badge ${styles[status] ?? styles.ARCHIVED}`}
    >
      <span className="status-dot" aria-hidden="true" />
      {status.replaceAll("_", " ")}
    </span>
  );
}
