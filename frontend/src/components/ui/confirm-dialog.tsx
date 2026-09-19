"use client";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  pending,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!open) return null;

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !pending) onCancel(); }}>
      <div
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        aria-modal="true"
        role="dialog"
        className="dialog-panel"
      >
        <div className="dialog-danger-icon" aria-hidden="true">!</div>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p id="confirm-dialog-description">
          {description}
        </p>
        <div className="dialog-actions">
          <button
            type="button"
            disabled={pending}
            onClick={onCancel}
            className="btn btn-secondary"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={onConfirm}
            className="btn btn-danger"
          >
            {pending ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
