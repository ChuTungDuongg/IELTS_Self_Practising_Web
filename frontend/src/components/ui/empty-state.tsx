import type { ReactNode } from "react";
import { LibraryIcon } from "./icons";

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">{icon ?? <LibraryIcon className="size-6" />}</div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
