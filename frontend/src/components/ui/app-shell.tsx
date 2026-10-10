"use client";

import type { ReactElement, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GlobalHeader } from "./global-header";
import { AppFooter } from "./app-footer";

function isBuilderPreview(pathname: string): boolean {
  return /^\/admin\/tests\/[^/]+\/versions\/[^/]+\/preview\/?$/.test(pathname);
}

export function AppShell({ children, currentYear }: { children: ReactNode; currentYear: number }): ReactElement {
  const pathname = usePathname() ?? "/";
  if (pathname.startsWith("/attempt/")) {
    return <main className="exam-shell">{children}</main>;
  }
  return <div className="app-shell">
    <GlobalHeader pathname={pathname} />
    <main className="app-content">{children}</main>
    {!isBuilderPreview(pathname) ? <AppFooter year={currentYear} /> : null}
  </div>;
}
