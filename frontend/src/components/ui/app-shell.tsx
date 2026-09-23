"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppLogo } from "./app-logo";
import { AnalyticsIcon, BuilderIcon, HistoryIcon, HomeIcon, LibraryIcon, TransferIcon } from "./icons";
import { ThemeToggle } from "./theme-toggle";
import { TRANSFER_ROUTE } from "@/lib/routes";
import { useAuth } from "@/features/auth/auth-provider";

const navigation = [
  { label: "Overview", href: "/", icon: HomeIcon },
  { label: "Test library", href: "/library", icon: LibraryIcon },
  { label: "Attempt history", href: "/history", icon: HistoryIcon },
  { label: "Analytics", href: "/analytics", icon: AnalyticsIcon },
] as const;
const adminNavigation = [
  { label: "Admin", href: "/admin", icon: BuilderIcon },
  { label: "Builder", href: "/admin/tests", icon: BuilderIcon },
  { label: "Transfer", href: TRANSFER_ROUTE, icon: TransferIcon },
] as const;

function isCurrent(pathname: string, href: string) {
  return href === "/" || href === "/admin" ? pathname === href : pathname.startsWith(href);
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { user, loading, sessionError, logout } = useAuth();
  const isExam = pathname.startsWith("/attempt/");
  const visibleNavigation = user ? [...navigation, ...(user.role === "ADMIN" ? adminNavigation : [])] : [navigation[0]];
  const current = visibleNavigation.find((item) => isCurrent(pathname, item.href));

  if (isExam) {
    return <main className="exam-shell">{children}</main>;
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link href="/" className="brand" aria-label="IELTS Studio overview">
          <span className="brand-mark" aria-hidden="true"><AppLogo variant="primary" /></span>
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
          {sessionError ? <p role="alert" className="notice">{sessionError}</p> : null}
          {!loading && user ? <><Link href="/profile" className="auth-user-label">{user.display_name}<small>{user.role}</small></Link><button type="button" className="btn btn-ghost" onClick={() => void logout()}>Logout</button></> : !loading && !sessionError ? <><Link href="/login" className="btn btn-ghost">Login</Link><Link href="/register" className="btn btn-primary">Register</Link></> : null}
          <ThemeToggle />
        </div>
      </header>

      <aside className="app-sidebar">
        <nav aria-label="Primary" className="sidebar-nav">
          <p className="sidebar-label">Workspace</p>
          {visibleNavigation.map((item) => {
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
