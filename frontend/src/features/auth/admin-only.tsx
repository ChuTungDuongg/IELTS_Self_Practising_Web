"use client";

import { useAuth } from "./auth-provider";

export function AdminOnly({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return user?.role === "ADMIN" ? children : null;
}
