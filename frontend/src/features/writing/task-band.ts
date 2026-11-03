/** Presentation compatibility only. FastAPI owns persisted scoring and weighting. */
export function taskBandFromRawMean(raw: number | null | undefined): number | null {
  if (raw == null || !Number.isFinite(raw) || raw < 0 || raw > 9) return null;
  // Raw criterion means are exact multiples of 0.125. For nonnegative bands,
  // Math.round matches backend Decimal ROUND_HALF_UP.
  return Math.round(raw * 2) / 2;
}

type TaskScore = {
  ta?: number | null;
  cc?: number | null;
  lr?: number | null;
  gra?: number | null;
  overall?: number | null;
  task_band?: number | null;
};

export function writingTaskBand(score: TaskScore | null | undefined): number | null {
  if (!score) return null;
  const criteria = [score.ta, score.cc, score.lr, score.gra];
  if (criteria.some(value => value == null || !Number.isFinite(value))) return null;
  return score.task_band ?? taskBandFromRawMean(
    criteria.reduce<number>((sum, value) => sum + value!, 0) / 4,
  );
}
