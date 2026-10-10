import type { ReactNode } from "react";

const modules = {
  READING: { label: "Reading", className: "module-reading" },
  LISTENING: { label: "Listening", className: "module-listening" },
  WRITING: { label: "Writing", className: "module-writing" },
} as const;

export function ModuleBadge({ module, label }: { module: keyof typeof modules; label?: ReactNode }) {
  const config = modules[module];
  return <span className={`module-badge ${config.className}`}>{label ?? config.label}</span>;
}
