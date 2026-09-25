"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { updateModuleDuration, type BuilderModule } from "@/lib/api/builder";
import { useBuilderAutosave } from "./builder-lifecycle";

function minutes(seconds: number | null): string {
  return seconds === null ? "" : String(seconds / 60);
}

export function ModuleDurationEditor({ module, onPersisted }: {
  module: BuilderModule;
  onPersisted?: (saved: BuilderModule) => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState(() => minutes(module.recommended_duration_seconds));
  const [error, setError] = useState<string | null>(null);
  const revision = useRef(module.revision);
  useEffect(() => {
    if (module.revision > revision.current) revision.current = module.revision;
  }, [module.revision]);
  const parsed = value.trim() === "" ? null : Number(value);
  const valid = parsed === null || (Number.isInteger(parsed) && parsed >= 1 && parsed <= 240);
  const { stageValue } = useBuilderAutosave({
    resourceKey: `module-duration:${module.id}`,
    value,
    valid,
    delay: 300,
    save: async (draft) => {
      try {
        const seconds = draft.trim() === "" ? null : Number(draft) * 60;
        const saved = await updateModuleDuration(module.id, revision.current, seconds);
        revision.current = saved.revision;
        setError(null);
        return saved;
      } catch (reason) {
        setError(reason instanceof ApiError ? reason.message : "Recommended duration could not be saved.");
        throw reason;
      }
    },
    onSaved: (saved, _submitted, unchanged) => {
      onPersisted?.(saved);
      router.refresh();
      if (unchanged) {
        const canonical = minutes(saved.recommended_duration_seconds);
        setValue(canonical);
        return canonical;
      }
    },
  });

  return <div className="mt-5">
    <label className="field-label" htmlFor={`module-duration-${module.id}`}>Recommended duration</label>
    <div className="mt-2 flex items-center gap-2">
      <input
        id={`module-duration-${module.id}`}
        aria-label="Recommended duration in minutes"
        className="field w-24"
        type="number"
        min="1"
        max="240"
        step="1"
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          const number = next.trim() === "" ? null : Number(next);
          setValue(next);
          stageValue(next, number === null || (Number.isInteger(number) && number >= 1 && number <= 240));
        }}
      />
      <span>minutes</span>
    </div>
    {error ? <p role="alert" className="notice notice-error mt-2">{error}</p> : null}
  </div>;
}
