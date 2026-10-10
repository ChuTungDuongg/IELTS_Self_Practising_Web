export function formatAudioTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "00:00";
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export function parseAudioTime(value: string): number | null {
  const match = /^(\d+):([0-5]\d)$/.exec(value.trim());
  if (!match) return null;
  const seconds = Number(match[1]) * 60 + Number(match[2]);
  return Number.isSafeInteger(seconds) ? seconds : null;
}

export type AudioClip = { startSeconds: number; endSeconds: number };

export function validAudioClip(clip: AudioClip): boolean {
  return Number.isInteger(clip.startSeconds) && Number.isInteger(clip.endSeconds)
    && clip.startSeconds >= 0 && clip.endSeconds > clip.startSeconds;
}

export function sectionAudioClip(section: { audio_start_seconds?: number | null; audio_end_seconds?: number | null }): AudioClip | undefined {
  if (section.audio_start_seconds == null || section.audio_end_seconds == null) return undefined;
  return { startSeconds: section.audio_start_seconds, endSeconds: section.audio_end_seconds };
}
