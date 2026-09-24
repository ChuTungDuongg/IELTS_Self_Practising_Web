"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { CheckIcon } from "@/components/ui/icons";
import { ApiError } from "@/lib/api/client";

export type AutosaveState = "SAVED" | "DIRTY" | "SAVING" | "ERROR" | "INVALID" | "CONFLICT";
type AutosaveController = { flush: () => Promise<boolean> };

type BuilderLifecycleValue = {
  deleting: boolean;
  mutating: boolean;
  transitioning: boolean;
  autosaveState: AutosaveState;
  runMutation: <T>(action: () => Promise<T>) => Promise<T>;
  runAutosave: <T>(key: string, action: () => Promise<T>) => Promise<T>;
  beginDelete: <T>(action: () => Promise<T>) => Promise<T>;
  runTransition: <T>(action: () => Promise<T>) => Promise<{ ready: true; value: T } | { ready: false }>;
  registerAutosave: (key: string, controller: AutosaveController) => () => void;
  setAutosaveState: (key: string, state: AutosaveState) => void;
  flushAutosaves: (excludeKey?: string) => Promise<boolean>;
};

const BuilderLifecycleContext = createContext<BuilderLifecycleValue | null>(null);
const standaloneAutosaveLifecycle = {
  registerAutosave: () => () => undefined,
  runAutosave: async <T,>(_key: string, action: () => Promise<T>) => action(),
  setAutosaveState: () => undefined,
};

export function BuilderLifecycleProvider({ children }: { children: React.ReactNode }) {
  const pending = useRef(new Set<Promise<unknown>>());
  const pendingMutations = useRef(new Set<Promise<unknown>>());
  const mutationTail = useRef<Promise<void> | null>(null);
  const autosaveTails = useRef(new Map<string, Promise<void>>());
  const deletingRef = useRef(false);
  const transitioningRef = useRef(false);
  const autosaves = useRef(new Map<string, AutosaveController>());
  const resourceStates = useRef(new Map<string, AutosaveState>());
  const barrierRevision = useRef(0);
  const [deleting, setDeleting] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [autosaveState, setAggregateState] = useState<AutosaveState>("SAVED");

  const recomputeState = useCallback(() => {
    const states = [...resourceStates.current.values()];
    const priority: AutosaveState[] = ["CONFLICT", "ERROR", "INVALID", "SAVING", "DIRTY", "SAVED"];
    setAggregateState(priority.find((state) => states.includes(state)) ?? "SAVED");
  }, []);

  const setAutosaveState = useCallback((key: string, state: AutosaveState) => {
    if (resourceStates.current.get(key) === state) return;
    resourceStates.current.set(key, state);
    barrierRevision.current += 1;
    recomputeState();
  }, [recomputeState]);

  const registerAutosave = useCallback((key: string, controller: AutosaveController) => {
    autosaves.current.set(key, controller);
    resourceStates.current.set(key, "SAVED");
    barrierRevision.current += 1;
    recomputeState();
    return () => {
      autosaves.current.delete(key);
      resourceStates.current.delete(key);
      barrierRevision.current += 1;
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
    pendingMutations.current.add(operation);
    setMutating(true);
    barrierRevision.current += 1;
    try { return await operation; }
    finally {
      pending.current.delete(operation);
      pendingMutations.current.delete(operation);
      setMutating(pendingMutations.current.size > 0);
      barrierRevision.current += 1;
      if (!pending.current.size) mutationTail.current = null;
    }
  }, []);

  const runAutosave = useCallback(async <T,>(key: string, action: () => Promise<T>): Promise<T> => {
    if (deletingRef.current) throw new Error("Draft deletion is in progress.");
    const previous = autosaveTails.current.get(key);
    let operation: Promise<T>;
    if (previous) operation = previous.then(action);
    else {
      try { operation = Promise.resolve(action()); }
      catch (error) { operation = Promise.reject(error); }
    }
    const tail = operation.then(() => undefined, () => undefined);
    autosaveTails.current.set(key, tail);
    pending.current.add(operation);
    try { return await operation; }
    finally {
      pending.current.delete(operation);
      if (autosaveTails.current.get(key) === tail) autosaveTails.current.delete(key);
    }
  }, []);

  const flushAutosaves = useCallback(async (excludeKey?: string) => {
    while (true) {
      const startingRevision = barrierRevision.current;
      // Explicit creates/reorders can unmount or replace an autosave controller.
      // Let them settle before asking the surviving editors to flush.
      const inFlightMutations = [...pendingMutations.current];
      if (inFlightMutations.length) {
        const mutations = await Promise.allSettled(inFlightMutations);
        if (mutations.some((result) => result.status === "rejected")) return false;
        continue;
      }

      const controllers = [...autosaves.current.entries()]
        .filter(([key]) => key !== excludeKey)
        .map(([, controller]) => controller);
      const results = await Promise.all(controllers.map((controller) => controller.flush()));
      if (!results.every(Boolean)) return false;
      // Controller and mutation state can change while Promise.all yields, even
      // when an observed mutation settles just before the pending snapshot.
      if (barrierRevision.current !== startingRevision) continue;
      return true;
    }
  }, []);

  const beginDelete = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    if (deletingRef.current) throw new Error("Draft deletion is already in progress.");
    setDeleting(true);
    try {
      if (!(await flushAutosaves())) throw new Error("Unsaved draft changes must be resolved before deletion.");
      deletingRef.current = true;
      await Promise.allSettled([...pending.current]);
      return await action();
    } catch (error) {
      deletingRef.current = false;
      setDeleting(false);
      throw error;
    }
  }, [flushAutosaves]);

  const runTransition = useCallback(async <T,>(action: () => Promise<T>): Promise<{ ready: true; value: T } | { ready: false }> => {
    if (transitioningRef.current || deletingRef.current) throw new Error("Another Builder transition is in progress.");
    transitioningRef.current = true;
    setTransitioning(true);
    try {
      if (!(await flushAutosaves())) return { ready: false };
      return { ready: true, value: await action() };
    } finally {
      transitioningRef.current = false;
      setTransitioning(false);
    }
  }, [flushAutosaves]);

  const value = useMemo(() => ({ deleting, mutating, transitioning, autosaveState, runMutation, runAutosave, beginDelete, runTransition, registerAutosave, setAutosaveState, flushAutosaves }), [deleting, mutating, transitioning, autosaveState, runMutation, runAutosave, beginDelete, runTransition, registerAutosave, setAutosaveState, flushAutosaves]);
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
  const lifecycle = useOptionalBuilderLifecycle();
  const { registerAutosave, runAutosave, setAutosaveState } = lifecycle ?? standaloneAutosaveLifecycle;
  const serialized = JSON.stringify(value);
  const baseline = useRef(serialized);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const drain = useRef<Promise<boolean> | null>(null);
  const conflicted = useRef(false);
  const registered = useRef(false);
  const valueRef = useRef(value);
  const serializedRef = useRef(serialized);
  const validRef = useRef(valid);
  const enabledRef = useRef(enabled);
  const saveRef = useRef(save);
  useLayoutEffect(() => {
    valueRef.current = value;
    serializedRef.current = serialized;
    validRef.current = valid;
    enabledRef.current = enabled;
    saveRef.current = save;
  }, [enabled, save, serialized, valid, value]);

  const flush = useCallback((): Promise<boolean> => {
    if (conflicted.current) return Promise.resolve(false);
    if (drain.current) return drain.current;
    const operation = (async (): Promise<boolean> => {
      while (true) {
        if (timer.current) clearTimeout(timer.current);
        timer.current = null;
        if (serializedRef.current === baseline.current) {
          setAutosaveState(resourceKey, "SAVED");
          return true;
        }
        if (!enabledRef.current) {
          setAutosaveState(resourceKey, validRef.current ? "DIRTY" : "INVALID");
          return false;
        }
        if (!validRef.current) {
          setAutosaveState(resourceKey, "INVALID");
          return false;
        }
        const savingValue = valueRef.current;
        const savingSerialized = serializedRef.current;
        setAutosaveState(resourceKey, "SAVING");
        try {
          await runAutosave(resourceKey, () => saveRef.current(savingValue));
          baseline.current = savingSerialized;
        } catch (error) {
          if (error instanceof ApiError && error.code === "DRAFT_REVISION_CONFLICT") {
            conflicted.current = true;
            setAutosaveState(resourceKey, "CONFLICT");
            return false;
          }
          if (serializedRef.current !== savingSerialized) continue;
          setAutosaveState(resourceKey, "ERROR");
          return false;
        }
        if (serializedRef.current !== savingSerialized) continue;
        setAutosaveState(resourceKey, "SAVED");
        return true;
      }
    })();
    drain.current = operation;
    void operation.finally(() => {
      if (drain.current === operation) drain.current = null;
    });
    return operation;
  }, [resourceKey, runAutosave, setAutosaveState]);

  useEffect(() => {
    registered.current = true;
    const unregister = registerAutosave(resourceKey, { flush });
    return () => {
      registered.current = false;
      unregister();
    };
  }, [flush, registerAutosave, resourceKey]);

  useEffect(() => {
    if (conflicted.current) {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      setAutosaveState(resourceKey, "CONFLICT");
      return;
    }
    if (serialized === baseline.current) {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      if (!drain.current) setAutosaveState(resourceKey, "SAVED");
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    if (!enabled) {
      setAutosaveState(resourceKey, valid ? "DIRTY" : "INVALID");
      return;
    }
    if (!valid) {
      setAutosaveState(resourceKey, "INVALID");
      return;
    }
    setAutosaveState(resourceKey, "DIRTY");
    timer.current = setTimeout(() => void flush(), delay);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [delay, enabled, flush, resourceKey, serialized, setAutosaveState, valid]);

  const markSaved = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    baseline.current = serializedRef.current;
    if (registered.current) setAutosaveState(resourceKey, "SAVED");
  }, [resourceKey, setAutosaveState]);

  return { saveNow: flush, markSaved };
}

export function BuilderAutosaveStatus() {
  const { autosaveState, flushAutosaves } = useBuilderLifecycle();
  const labels: Record<AutosaveState, string> = { SAVED: "Saved", DIRTY: "Unsaved changes", SAVING: "Saving…", ERROR: "Save failed", INVALID: "Unsaved — fix validation issues", CONFLICT: "This content changed in another tab or by another admin. Reload the latest version before continuing." };
  return <div className="save-status" role="status" aria-live="polite"><span className={autosaveState === "ERROR" || autosaveState === "INVALID" || autosaveState === "CONFLICT" ? "save-status-error" : ""}><CheckIcon className="size-4" /> {labels[autosaveState]}</span>{autosaveState === "ERROR" || autosaveState === "DIRTY" ? <button type="button" className="btn btn-ghost" onClick={() => void flushAutosaves()}>{autosaveState === "ERROR" ? "Retry" : "Save now"}</button> : null}{autosaveState === "CONFLICT" ? <button type="button" className="btn btn-ghost" onClick={() => window.location.reload()}>Reload latest</button> : null}</div>;
}
