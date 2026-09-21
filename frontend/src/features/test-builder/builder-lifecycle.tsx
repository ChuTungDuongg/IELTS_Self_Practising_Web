"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { CheckIcon } from "@/components/ui/icons";

export type AutosaveState = "SAVED" | "DIRTY" | "SAVING" | "ERROR" | "INVALID";
type AutosaveController = { flush: () => Promise<boolean> };

type BuilderLifecycleValue = {
  deleting: boolean;
  autosaveState: AutosaveState;
  runMutation: <T>(action: () => Promise<T>) => Promise<T>;
  beginDelete: <T>(action: () => Promise<T>) => Promise<T>;
  registerAutosave: (key: string, controller: AutosaveController) => () => void;
  setAutosaveState: (key: string, state: AutosaveState) => void;
  flushAutosaves: () => Promise<boolean>;
};

const BuilderLifecycleContext = createContext<BuilderLifecycleValue | null>(null);

export function BuilderLifecycleProvider({ children }: { children: React.ReactNode }) {
  const pending = useRef(new Set<Promise<unknown>>());
  const mutationTail = useRef<Promise<void> | null>(null);
  const deletingRef = useRef(false);
  const autosaves = useRef(new Map<string, AutosaveController>());
  const resourceStates = useRef(new Map<string, AutosaveState>());
  const [deleting, setDeleting] = useState(false);
  const [autosaveState, setAggregateState] = useState<AutosaveState>("SAVED");

  const recomputeState = useCallback(() => {
    const states = [...resourceStates.current.values()];
    const priority: AutosaveState[] = ["ERROR", "INVALID", "SAVING", "DIRTY", "SAVED"];
    setAggregateState(priority.find((state) => states.includes(state)) ?? "SAVED");
  }, []);

  const setAutosaveState = useCallback((key: string, state: AutosaveState) => {
    resourceStates.current.set(key, state);
    recomputeState();
  }, [recomputeState]);

  const registerAutosave = useCallback((key: string, controller: AutosaveController) => {
    autosaves.current.set(key, controller);
    resourceStates.current.set(key, "SAVED");
    recomputeState();
    return () => {
      autosaves.current.delete(key);
      resourceStates.current.delete(key);
      recomputeState();
    };
  }, [recomputeState]);

  const runMutation = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    if (deletingRef.current) throw new Error("Draft deletion is in progress.");
    let operation: Promise<T>;
    if (mutationTail.current) operation = mutationTail.current.then(action);
    else {
      try { operation = Promise.resolve(action()); }
      catch (error) { operation = Promise.reject(error); }
    }
    mutationTail.current = operation.then(() => undefined, () => undefined);
    pending.current.add(operation);
    try { return await operation; }
    finally {
      pending.current.delete(operation);
      if (!pending.current.size) mutationTail.current = null;
    }
  }, []);

  const flushAutosaves = useCallback(async () => {
    const results = await Promise.all([...autosaves.current.values()].map((controller) => controller.flush()));
    return results.every(Boolean);
  }, []);

  const beginDelete = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    if (deletingRef.current) throw new Error("Draft deletion is already in progress.");
    await flushAutosaves();
    deletingRef.current = true;
    setDeleting(true);
    try {
      await Promise.allSettled([...pending.current]);
      return await action();
    } catch (error) {
      deletingRef.current = false;
      setDeleting(false);
      throw error;
    }
  }, [flushAutosaves]);

  const value = useMemo(() => ({ deleting, autosaveState, runMutation, beginDelete, registerAutosave, setAutosaveState, flushAutosaves }), [deleting, autosaveState, runMutation, beginDelete, registerAutosave, setAutosaveState, flushAutosaves]);
  return <BuilderLifecycleContext.Provider value={value}>{children}</BuilderLifecycleContext.Provider>;
}

export function useBuilderLifecycle(): BuilderLifecycleValue {
  const value = useContext(BuilderLifecycleContext);
  if (!value) throw new Error("Builder lifecycle context is unavailable.");
  return value;
}

export function useOptionalBuilderLifecycle(): BuilderLifecycleValue | null {
  return useContext(BuilderLifecycleContext);
}

export function useBuilderAutosave<T>({ resourceKey, value, save, valid = true, enabled = true, delay = 1000 }: {
  resourceKey: string;
  value: T;
  save: (value: T) => Promise<unknown>;
  valid?: boolean;
  enabled?: boolean;
  delay?: number;
}) {
  const { registerAutosave, runMutation, setAutosaveState } = useBuilderLifecycle();
  const serialized = JSON.stringify(value);
  const baseline = useRef(serialized);
  const generation = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const valueRef = useRef(value);
  const serializedRef = useRef(serialized);
  const validRef = useRef(valid);
  const enabledRef = useRef(enabled);
  const saveRef = useRef(save);
  useEffect(() => {
    valueRef.current = value;
    serializedRef.current = serialized;
    validRef.current = valid;
    enabledRef.current = enabled;
    saveRef.current = save;
  }, [enabled, save, serialized, valid, value]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    while (true) {
      if (!enabledRef.current || serializedRef.current === baseline.current) {
        setAutosaveState(resourceKey, "SAVED");
        return true;
      }
      if (!validRef.current) {
        setAutosaveState(resourceKey, "INVALID");
        return false;
      }
      const savingGeneration = generation.current;
      const savingValue = valueRef.current;
      const savingSerialized = serializedRef.current;
      setAutosaveState(resourceKey, "SAVING");
      try {
        await runMutation(() => saveRef.current(savingValue));
        if (generation.current !== savingGeneration) continue;
        baseline.current = savingSerialized;
        setAutosaveState(resourceKey, "SAVED");
        return true;
      } catch {
        if (generation.current === savingGeneration) setAutosaveState(resourceKey, "ERROR");
        return false;
      }
    }
  }, [resourceKey, runMutation, setAutosaveState]);

  useEffect(() => registerAutosave(resourceKey, { flush }), [flush, registerAutosave, resourceKey]);

  useEffect(() => {
    if (!enabled || serialized === baseline.current) return;
    generation.current += 1;
    if (timer.current) clearTimeout(timer.current);
    if (!valid) {
      setAutosaveState(resourceKey, "INVALID");
      return;
    }
    setAutosaveState(resourceKey, "DIRTY");
    timer.current = setTimeout(() => void flush(), delay);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [delay, enabled, flush, resourceKey, serialized, setAutosaveState, valid]);

  return { saveNow: flush };
}

export function BuilderAutosaveStatus() {
  const { autosaveState, flushAutosaves } = useBuilderLifecycle();
  const labels: Record<AutosaveState, string> = { SAVED: "Saved", DIRTY: "Unsaved changes", SAVING: "Saving…", ERROR: "Save failed", INVALID: "Unsaved — fix validation issues" };
  return <div className="save-status" role="status" aria-live="polite"><span className={autosaveState === "ERROR" || autosaveState === "INVALID" ? "save-status-error" : ""}><CheckIcon className="size-4" /> {labels[autosaveState]}</span>{autosaveState === "ERROR" || autosaveState === "DIRTY" ? <button type="button" className="btn btn-ghost" onClick={() => void flushAutosaves()}>{autosaveState === "ERROR" ? "Retry" : "Save now"}</button> : null}</div>;
}
