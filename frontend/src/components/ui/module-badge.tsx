const modules = {
  READING: { label: "Reading", className: "module-reading" },
  LISTENING: { label: "Listening", className: "module-listening" },
  WRITING: { label: "Writing", className: "module-writing" },
} as const;

export function ModuleBadge({ module }: { module: keyof typeof modules }) {
  const config = modules[module];
  return <span className={`module-badge ${config.className}`}>{config.label}</span>;
}
