export function estimateServerOffset(serverTime: string, receivedAt = Date.now()): number {
  return new Date(serverTime).getTime() - receivedAt;
}

export function remainingSeconds(deadlineAt: string, serverOffsetMs: number, now = Date.now()): number {
  return Math.max(0, Math.ceil((new Date(deadlineAt).getTime() - (now + serverOffsetMs)) / 1000));
}

export function elapsedSeconds(startedAt: string, serverOffsetMs: number, now = Date.now()): number {
  return Math.max(0, Math.floor((now + serverOffsetMs - new Date(startedAt).getTime()) / 1000));
}

export function elapsedFromSnapshot(
  elapsedAtSnapshot: number,
  serverTime: string,
  serverOffsetMs: number,
  now = Date.now(),
): number {
  const secondsSinceSnapshot = Math.floor(
    (now + serverOffsetMs - new Date(serverTime).getTime()) / 1000,
  );
  return Math.max(0, elapsedAtSnapshot + secondsSinceSnapshot);
}

export function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const base = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return hours ? `${String(hours).padStart(2, "0")}:${base}` : base;
}
