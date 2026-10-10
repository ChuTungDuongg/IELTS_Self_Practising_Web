"use client";

import { useTranslation } from "@/lib/i18n/locale-provider";

import { useRef, useState } from "react";
import { formatAudioTime, parseAudioTime, type AudioClip } from "@/features/listening/audio-time";
import { updateListeningPart, type BuilderListeningPart } from "@/lib/api/builder";
import { useBuilderAutosave } from "./builder-lifecycle";

type SectionFields = { title: string; start: string; end: string };
function fields(part: BuilderListeningPart): SectionFields {
  return {
    title: part.title ?? `Section ${part.order_index + 1}`,
    start: part.audio_start_seconds == null ? "" : formatAudioTime(part.audio_start_seconds),
    end: part.audio_end_seconds == null ? "" : formatAudioTime(part.audio_end_seconds),
  };
}

export function ListeningSectionEditor({ part, duration, currentPosition, onPreview, onPersisted }: {
  part: BuilderListeningPart;
  duration: number | null;
  currentPosition: () => number;
  onPreview: (clip: AudioClip) => void;
  onPersisted: (part: BuilderListeningPart) => void;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState(() => fields(part));
  const revision = useRef(part.revision);
  function validation(next: SectionFields): string | null {
    if (!next.title.trim() || next.title.length > 240) return "Enter a section title of 1–240 characters.";
    if (!next.start.trim() && !next.end.trim()) return null;
    const start = parseAudioTime(next.start), end = parseAudioTime(next.end);
    if (start === null || end === null) return "Enter both start and end in MM:SS format (for example 07:48).";
    if (end <= start) return "Audio end must be later than audio start.";
    if (duration !== null && end > duration) return "Audio end exceeds the recording duration. Correct the range before saving.";
    return null;
  }
  const error = validation(value);
  const autosave = useBuilderAutosave({ resourceKey: `listening-part:${part.id}`, value, valid: error === null,
    save: async (next) => {
      const saved = await updateListeningPart(part.id, { title: next.title, order_index: part.order_index,
        audio_start_seconds: next.start.trim() ? parseAudioTime(next.start) : null,
        audio_end_seconds: next.end.trim() ? parseAudioTime(next.end) : null, expected_revision: revision.current });
      revision.current = saved.revision;
      return saved;
    }, onSaved: (saved, _submitted, unchanged) => {
      onPersisted(saved);
      if (unchanged) { const canonical = fields(saved); setValue(canonical); return canonical; }
    },
  });
  function change(patch: Partial<SectionFields>) {
    const next = { ...value, ...patch };
    autosave.stageValue(next, validation(next) === null);
    setValue(next);
  }
  const clip = { startSeconds: parseAudioTime(value.start) ?? 0, endSeconds: parseAudioTime(value.end) ?? 0 };
  return <div>
    <label className="field-label mb-4 block">{t("builder.sectionTitle")}<input className="field mt-2" value={value.title} onChange={(event) => change({ title: event.target.value })} /></label>
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="field-label">Audio start (MM:SS)<input className="field mt-2" placeholder="07:48" value={value.start} aria-describedby={`audio-range-${part.id}`} onChange={(event) => change({ start: event.target.value })} /></label>
      <label className="field-label">Audio end (MM:SS)<input className="field mt-2" placeholder="15:31" value={value.end} aria-describedby={`audio-range-${part.id}`} onChange={(event) => change({ end: event.target.value })} /></label>
    </div>
    <p id={`audio-range-${part.id}`} className="mt-2 text-sm text-[var(--muted)]">Optional for full Listening. Set both times to enable focused section practice.{duration !== null ? ` Recording duration: ${formatAudioTime(duration)}.` : " Load the recording to check its duration."}</p>
    {error ? <p role="alert" className="notice notice-error mt-2">{error}</p> : null}
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" className="btn btn-secondary" disabled={duration === null} onClick={() => change({ start: formatAudioTime(Math.floor(currentPosition())) })}>Set start to current position</button>
      <button type="button" className="btn btn-secondary" disabled={duration === null} onClick={() => change({ end: formatAudioTime(Math.floor(currentPosition())) })}>Set end to current position</button>
      <button type="button" className="btn btn-listening" disabled={duration === null || Boolean(error) || !value.start || !value.end} onClick={() => onPreview(clip)}>Preview section clip</button>
      <button type="button" className="btn btn-secondary" onClick={() => change({ start: "", end: "" })}>Clear audio range</button>
    </div>
  </div>;
}
