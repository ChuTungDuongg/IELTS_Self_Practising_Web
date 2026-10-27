"use client";
import { createContext, useContext } from "react";
export const AssignmentSyncContext = createContext<(() => Promise<unknown>) | undefined>(undefined);
export function useAssignmentSync() { return useContext(AssignmentSyncContext); }
