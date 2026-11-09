"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import styles from "./navigation.module.css";

/** Keep every editor mounted: navigating a work area must never discard its draft. */
export function PersistentSections({ label, sections, compact = false }: {
  label: string;
  sections: { id: string; label: string; content: ReactNode }[];
  compact?: boolean;
}) {
  const id = useId();
  const [selected, setSelected] = useState(sections[0].id);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  return <div className={compact ? styles.tasks : styles.workAreas}>
    {!compact && <label className={styles.mobileSelector}>{label}
      <select className="field" value={selected} onChange={event => setSelected(event.target.value)} aria-controls={`${id}-panel-${selected}`}>
        {sections.map(section => <option key={section.id} value={section.id}>{section.label}</option>)}
      </select>
    </label>}
    <div className={styles.tabs} role="tablist" aria-label={label}>
      {sections.map((section, index) => <button key={section.id} type="button" ref={node => { buttons.current[index] = node; }} role="tab" id={`${id}-tab-${section.id}`} aria-controls={`${id}-panel-${section.id}`} aria-selected={selected === section.id} tabIndex={selected === section.id ? 0 : -1} onClick={() => setSelected(section.id)} onKeyDown={event => {
        let next: number;
        if (event.key === "ArrowRight") next = (index + 1) % sections.length;
        else if (event.key === "ArrowLeft") next = (index + sections.length - 1) % sections.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = sections.length - 1;
        else return;
        event.preventDefault();
        setSelected(sections[next].id);
        buttons.current[next]?.focus();
      }}>{section.label}</button>)}
    </div>
    {sections.map(section => <div key={section.id} id={`${id}-panel-${section.id}`} role="tabpanel" aria-labelledby={`${id}-tab-${section.id}`} hidden={selected !== section.id} tabIndex={0}>{section.content}</div>)}
  </div>;
}
