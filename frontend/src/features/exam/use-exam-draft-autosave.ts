"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  ExamDraftStore, isTerminalAttempt,
  type DraftMetadata, type RecoveryConflict, type ServerResponse,
} from "./exam-draft-recovery";
import { useRevisionAutosave, type AutosaveCallbacks } from "./revision-autosave";

export function useExamDraftAutosave<Value>({
  attempt,
  initialResponses,
  save,
  debounceMs,
}: {
  attempt: DraftMetadata & { status: "IN_PROGRESS" | "PAUSED" | "SUBMITTED" | "AUTO_SUBMITTED" | "INTERRUPTED" | "ABANDONED" };
  initialResponses: ServerResponse<Value>[];
  save: (id: string, value: Value, expectedRevision: number) => Promise<{ revision: number }>;
  debounceMs: number;
}) {
  const attemptId = attempt.attempt_id;
  const testVersionId = attempt.test_version_id;
  const attemptModule = attempt.module;
  const store = useMemo(() => new ExamDraftStore({
    attempt_id: attemptId, test_version_id: testVersionId, module: attemptModule,
  }), [attemptId, testVersionId, attemptModule]);
  const revisions = useRef<Record<string, number>>(
    Object.fromEntries(initialResponses.map(({ id, revision }) => [id, revision])),
  );
  const [values, setValues] = useState<Record<string, Value>>(() =>
    Object.fromEntries(initialResponses.map(({ id, value }) => [id, value])),
  );
  const [conflicts, setConflicts] = useState<Record<string, RecoveryConflict<Value>>>({});
  const [recoveredIds, setRecoveredIds] = useState<string[]>([]);
  const conflictRef = useRef<Record<string, RecoveryConflict<Value>>>({});
  const editedKeys = useRef(new Set<string>());
  const restoredAttemptState = useRef<string | null>(null);
  const recoveredSnapshot = useRef<{
    safe: Array<{ id: string; value: Value }>;
    conflicts: Array<RecoveryConflict<Value>>;
  }>({ safe: [], conflicts: [] });

  const send = useCallback(async (id: string, value: Value) => {
    const response = await save(id, value, revisions.current[id] ?? 0);
    revisions.current[id] = response.revision;
    return response;
  }, [save]);
  const callbacks = useMemo<AutosaveCallbacks<Value>>(() => ({
    onDirty: (id, value) => store.saveEntry(id, value, revisions.current[id] ?? 0),
    onAcknowledged: (id, currentValue, isLatest) => {
      if (isLatest) store.removeEntry(id);
      else store.saveEntry(id, currentValue, revisions.current[id] ?? 0);
    },
  }), [store]);
  const { queue, status, offline } = useRevisionAutosave(send, debounceMs, callbacks, true);

  useEffect(() => {
    const stateKey = `${attempt.attempt_id}:${attempt.status}`;
    if (restoredAttemptState.current !== stateKey) {
      restoredAttemptState.current = stateKey;
      if (isTerminalAttempt(attempt.status)) { store.clear(); return; }
      const recovered = store.reconcile(initialResponses);
      recoveredSnapshot.current = recovered;
      conflictRef.current = Object.fromEntries(recovered.conflicts.map((conflict) => [conflict.id, conflict]));
      if (attempt.status === "IN_PROGRESS") {
        recovered.safe.forEach(({ id, value }) => queue.markDirty(id, value));
      }
    }
    let active = true;
    // Apply the display update after hydration; the storage read above precedes user edits.
    queueMicrotask(() => {
      if (!active) return;
      const recovered = recoveredSnapshot.current;
      setRecoveredIds(recovered.safe.map(({ id }) => id));
      if (recovered.safe.length) {
        setValues((current) => ({ ...current, ...Object.fromEntries(recovered.safe
          .filter(({ id }) => !editedKeys.current.has(id)).map(({ id, value }) => [id, value])) }));
      }
      if (recovered.conflicts.length) {
        setConflicts(Object.fromEntries(recovered.conflicts.map((conflict) => [conflict.id, conflict])));
      }
    });
    return () => { active = false; };
  }, [attempt.attempt_id, attempt.status, initialResponses, queue, store]);

  const edit = useCallback((id: string, value: Value): boolean => {
    if (conflictRef.current[id]) {
      setValues((current) => ({ ...current }));
      return false;
    }
    editedKeys.current.add(id);
    setValues((current) => ({ ...current, [id]: value }));
    queue.markDirty(id, value);
    return true;
  }, [queue]);

  const resolveConflict = useCallback((id: string, choice: "saved" | "recovered") => {
    const conflict = conflicts[id];
    if (!conflict) return;
    delete conflictRef.current[id];
    if (choice === "recovered") {
      revisions.current[id] = conflict.serverRevision;
      setValues((current) => ({ ...current, [id]: conflict.localValue }));
      if (attempt.status === "IN_PROGRESS") queue.markDirty(id, conflict.localValue);
      else store.saveEntry(id, conflict.localValue, conflict.serverRevision);
      setRecoveredIds((current) => [...current, id]);
    } else {
      store.removeEntry(id);
      setRecoveredIds((current) => current.filter((item) => item !== id));
    }
    setConflicts((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }, [attempt.status, conflicts, queue, store]);

  const flush = useCallback(async () => {
    await queue.flush();
    if (Object.keys(conflicts).length) {
      throw new ApiError("RECOVERY_CONFLICT", "Resolve recovered response conflicts before continuing.", 409);
    }
  }, [conflicts, queue]);

  return { queue, status, offline, values, conflicts, recoveredIds, edit, resolveConflict, flush };
}
