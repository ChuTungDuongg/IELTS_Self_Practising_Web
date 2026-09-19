"use client";

import { createContext, useContext, useRef, useState } from "react";

type BuilderLifecycleValue = {
  deleting: boolean;
  runMutation: <T>(action: () => Promise<T>) => Promise<T>;
  beginDelete: <T>(action: () => Promise<T>) => Promise<T>;
};

const BuilderLifecycleContext = createContext<BuilderLifecycleValue | null>(null);

export function BuilderLifecycleProvider({ children }: { children: React.ReactNode }) {
  const pending = useRef(new Set<Promise<unknown>>());
  const mutationTail = useRef<Promise<void> | null>(null);
  const deletingRef = useRef(false);
  const [deleting, setDeleting] = useState(false);

  async function runMutation<T>(action: () => Promise<T>): Promise<T> {
    if (deletingRef.current) {
      throw new Error("Draft deletion is in progress.");
    }
    let operation: Promise<T>;
    if (mutationTail.current) {
      operation = mutationTail.current.then(action);
    } else {
      try {
        operation = Promise.resolve(action());
      } catch (error) {
        operation = Promise.reject(error);
      }
    }
    mutationTail.current = operation.then(
      () => undefined,
      () => undefined,
    );
    pending.current.add(operation);
    try {
      return await operation;
    } finally {
      pending.current.delete(operation);
      if (!pending.current.size) mutationTail.current = null;
    }
  }

  async function beginDelete<T>(action: () => Promise<T>): Promise<T> {
    if (deletingRef.current) {
      throw new Error("Draft deletion is already in progress.");
    }
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
  }

  return (
    <BuilderLifecycleContext.Provider value={{ deleting, runMutation, beginDelete }}>
      {children}
    </BuilderLifecycleContext.Provider>
  );
}

export function useBuilderLifecycle(): BuilderLifecycleValue {
  const value = useContext(BuilderLifecycleContext);
  if (!value) throw new Error("Builder lifecycle context is unavailable.");
  return value;
}
