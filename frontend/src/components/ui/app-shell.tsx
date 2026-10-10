"use client";

import type { ReactElement, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GlobalHeader } from "./global-header";
import { AppFooter } from "./app-footer";

function isBuilderPreview(pathname: string): boolean {
  return /^\/admin\/tests\/[^/]+\/versions\/[^/]+\/preview\/?$/.test(pathname);
}

function contentWidth(pathname: string): "standard" | "wide" {
  const path = pathname.replace(/\/$/, "") || "/";
  if (
    path === "/admin/tests/new" ||
    /^\/library\/[^/]+$/.test(path) ||
    /^\/admin\/users\/[^/]+$/.test(path) ||
    /^\/admin\/tests\/[^/]+$/.test(path)
  ) return "standard";

  if (
    ["/library", "/practice", "/history", "/analytics", "/admin", "/admin/users", "/admin/tests", "/transfer"].includes(path) ||
    path.startsWith("/admin/tests/")
  ) return "wide";

  return "standard";
}

export function AppShell({ children, currentYear }: { children: ReactNode; currentYear: number }): ReactElement {
  const pathname = usePathname() ?? "/";
  if (pathname.startsWith("/attempt/")) {
    return <main className="exam-shell">{children}</main>;
  }
  return <div className="app-shell">
    <GlobalHeader pathname={pathname} />
    <main className={`app-content app-content-${contentWidth(pathname)}`}>{children}</main>
    {!isBuilderPreview(pathname) ? <AppFooter year={currentYear} /> : null}
  </div>;
}
