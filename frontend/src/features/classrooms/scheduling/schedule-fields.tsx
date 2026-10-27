"use client";
import type { SchedulePolicy } from "@/lib/api/assignment-scheduling";
import { localDateTime } from "@/lib/api/assignment-scheduling";
import { useScheduleText } from "./messages";
export function ScheduleFields({ value }: { value?: Partial<SchedulePolicy> }) {
  const { st } = useScheduleText();
  return <fieldset className="assignment-schedule-fields"><legend>{st("schedule")}</legend><p className="classroom-meta">{st("timezone")} · {Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
    {([ ["available_from", "available"], ["due_at", "due"], ["cutoff_at", "cutoff"] ] as const).map(([name, key]) => <label className="field-label" key={name}>{st(key)}<input className="field" name={name} type="datetime-local" defaultValue={localDateTime(value?.[name])} /></label>)}
    <label className="field-label">{st("maxAttempts")}<input className="field" name="max_attempts" type="number" min={1} max={10000} step={1} defaultValue={value?.max_attempts ?? ""} placeholder={st("unlimited")} /></label>
    <label><input type="checkbox" name="allow_late_submission" defaultChecked={value?.allow_late_submission ?? true} /> {st("allowLate")}</label>
    <p className="classroom-meta">{st("sharedLimit")}</p><p className="classroom-meta">{st("noCutoff")}</p>
  </fieldset>;
}
