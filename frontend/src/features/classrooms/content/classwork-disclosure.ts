"use client";

import { useEffect, useRef, useState } from "react";
import type { ClassworkGroup } from "./classwork-groups";

export function useClassworkDisclosure(groups: ClassworkGroup[]) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const first = groups.find(group => group.kind === "topic" && group.section?.status === "PUBLISHED" && group.rows.some(row => row.assignment?.status === "ACTIVE" || row.resource?.status === "PUBLISHED"));
    return first ? { [first.key]: true } : {};
  });
  const handled = useRef<string | null>(null);
  const [focus, setFocus] = useState<{ hash: string; id: string } | null>(null);
  useEffect(() => {
    function navigate() {
      const hash = window.location.hash.slice(1);
      if (hash === handled.current) return;
      if (!hash) { handled.current = hash; return; }
      const group = groups.find(group => group.key === hash || group.rows.some(row => row.key === hash || "classwork-" + row.key === hash || row.item && "item-" + row.item.id === hash));
      if (!group) return;
      handled.current = hash;
      const row = group.rows.find(row => row.key === hash || "classwork-" + row.key === hash || row.item && "item-" + row.item.id === hash);
      setExpanded(previous => ({ ...previous, [group.key]: true }));
      setFocus({ hash, id: row ? "classwork-" + row.key : group.key + "-toggle" });
    }
    navigate(); window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, [groups]);
  useEffect(() => {
    if (!focus) return;
    const target = document.getElementById(focus.id);
    target?.focus({ preventScroll: true }); target?.scrollIntoView?.({ block: "nearest" });
  }, [focus]);
  return { expanded, toggle: (key: string) => setExpanded(previous => ({ ...previous, [key]: !previous[key] })) };
}
