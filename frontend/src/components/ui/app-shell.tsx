"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BuilderIcon, HistoryIcon, HomeIcon, LibraryIcon } from "./icons";
import { ThemeToggle } from "./theme-toggle";

const navigation = [
  { label: "Overview", href: "/", icon: HomeIcon },
  { label: "Test library", href: "/library", icon: LibraryIcon },
  { label: "Builder", href: "/admin/tests", icon: BuilderIcon },
  { label: "Attempt history", href: "/history", icon: HistoryIcon },
] as const;

function isCurrent(pathname: string, href: string) {
  return href === "/" ? pathname === href : pathname.startsWith(href);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const isExam = pathname.startsWith("/attempt/");
  const current = navigation.find((item) => isCurrent(pathname, item.href));

  if (isExam) {
    return <main className="exam-shell">{children}</main>;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link href="/" className="brand" aria-label="IELTS Studio overview">
          <span className="brand-mark" aria-hidden="true">IS</span>
          <span>
            <strong>IELTS Studio</strong>
            <small>Practice & authoring</small>
          </span>
        </Link>
        <div className="header-context" aria-label="Current section">
          <span className="header-context-label">Workspace</span>
          <span>{current?.label ?? "IELTS Studio"}</span>
        </div>
        <div className="header-actions">
          <span className="local-badge"><span aria-hidden="true" /> Local workspace</span>
          <ThemeToggle />
        </div>
      </header>

      <aside className="app-sidebar">
        <nav aria-label="Primary" className="sidebar-nav">
          <p className="sidebar-label">Workspace</p>
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = isCurrent(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`sidebar-item ${active ? "sidebar-item-active" : ""}`}
              >
                <Icon className="size-5 shrink-0" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-note-icon" aria-hidden="true">40</span>
          <div>
            <strong>Built for focus</strong>
            <p>Structured authoring with frozen published versions.</p>
          </div>
        </div>
      </aside>

      <main className="app-content">{children}</main>
    </div>
  );
}
