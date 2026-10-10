"use client";

import type { ReactElement, ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GlobalHeader } from "./global-header";

export function AppShell({ children, currentYear }: { children: ReactNode; currentYear: number }): ReactElement {
  // Accepted now for the shared footer integration in Task 4.
  void currentYear;
  const pathname = usePathname() ?? "/";
  if (pathname.startsWith("/attempt/")) {
    return <main className="exam-shell">{children}</main>;
  }
  return <div className="app-shell">
    <GlobalHeader pathname={pathname} />
    <main className="app-content">{children}</main>
  </div>;
}
