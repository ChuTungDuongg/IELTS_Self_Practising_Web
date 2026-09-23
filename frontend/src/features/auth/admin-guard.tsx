"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./auth-provider";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname() ?? "/admin";

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [loading, pathname, router, user]);

  if (loading || !user) return <p className="notice">Checking administrator access…</p>;
  if (user.role !== "ADMIN") {
    return <section className="empty-state"><h1>Forbidden</h1><p>This workspace is available to administrators only.</p></section>;
  }
  return children;
}
