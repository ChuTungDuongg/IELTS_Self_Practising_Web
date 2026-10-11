"use client";

import { useRef, useState, type ReactElement } from "react";
import Link from "next/link";
import { AppLogo } from "./app-logo";
import { ConfirmDialog } from "./confirm-dialog";
import { ThemeToggle } from "./theme-toggle";
import { TRANSFER_ROUTE } from "@/lib/routes";
import { useAuth } from "@/features/auth/auth-provider";
import { useLocale, useTranslation } from "@/lib/i18n/locale-provider";
import { roleTranslationKeys } from "@/lib/i18n/translations";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { usePersonalization } from "@/features/personalization/personalization-provider";
import { PersonalizationError } from "@/features/personalization/personalization-settings";
import { SettingsIcon } from "./icons";

const navigation = [
  { message: "shell.overview", href: "/" },
  { message: "shell.library", href: "/library" },
  { message: "shell.practice", href: "/practice" },
  { message: "shell.history", href: "/history" },
  { message: "shell.analytics", href: "/analytics" },
] as const;
const adminNavigation = [
  { message: "shell.admin", href: "/admin" },
  { message: "shell.builder", href: "/admin/tests" },
  { message: "shell.transfer", href: TRANSFER_ROUTE },
  { message: "shell.moderation", href: "/admin/moderation" },
  { message: "shell.classrooms", href: "/classrooms" },
] as const;
const teacherNavigation = [{ message: "shell.builder", href: "/teacher/tests" }, { message: "shell.classrooms", href: "/teacher/classrooms" }] as const;

function isCurrent(pathname: string, href: string) {
  return href === "/" || href === "/admin" ? pathname === href : pathname.startsWith(href);
}

function PrimaryNavigation({ pathname }: { pathname: string }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const visibleNavigation = user ? [...navigation, ...(user.role === "ADMIN" ? adminNavigation : user.role === "TEACHER" ? teacherNavigation : [{ message: "shell.classrooms" as const, href: "/classrooms" }])] : [navigation[0]];
  return (
    <nav aria-label={t("shell.primary")} className="primary-nav">
      <ul className="primary-nav-list">
        {visibleNavigation.map((item) => {
          const active = isCurrent(pathname, item.href);
          return <li key={item.href}><Link href={item.href} prefetch={item.href === "/" ? undefined : false} aria-current={active ? "page" : undefined} className={`primary-nav-link ${active ? "primary-nav-link-active" : ""}`}>{t(item.message)}</Link></li>;
        })}
      </ul>
    </nav>
  );
}

function LocaleSwitcher() {
  const { locale, setLocale } = useLocale();
  const { t } = useTranslation();
  const { canUpdate } = usePersonalization();
  return <div className="locale-switcher" role="group" aria-label={t("shell.language")}>
    <button type="button" lang="en" aria-label="English" aria-pressed={locale === "en"} disabled={!canUpdate} onClick={() => setLocale("en")}>EN</button>
    <button type="button" lang="vi" aria-label="Tiếng Việt" aria-pressed={locale === "vi"} disabled={!canUpdate} onClick={() => setLocale("vi")}>VI</button>
  </div>;
}

function HeaderActions({ loggingOut, onLogout, pathname }: { loggingOut: boolean; onLogout(): void; pathname: string }) {
  const { user, loading, sessionError } = useAuth();
  const { t } = useTranslation();
  return <div className="header-actions">
    <LocaleSwitcher />
    <ThemeToggle />
    {user ? <Link href="/settings/personalization" prefetch={false} className="icon-button" aria-label={t("personalization.title")} title={t("personalization.title")}><SettingsIcon width="20" height="20" /></Link> : null}
    {!pathname.startsWith("/settings/personalization") ? <PersonalizationError /> : null}
    {user ? <NotificationCenter key={user.id} userId={user.id} /> : null}
    {sessionError ? <p role="alert" className="notice">{sessionError}</p> : null}
    {!loading && user ? <><Link href="/profile" prefetch={false} className="auth-user-label"><span className="auth-user-name">{user.display_name}</span><small>{t(roleTranslationKeys[user.role])}</small></Link><button type="button" className="btn btn-ghost" disabled={loggingOut} onClick={onLogout}>{t("shell.logout")}</button></> : !loading && !sessionError ? <><Link href="/login" prefetch={false} className="btn btn-ghost">{t("shell.login")}</Link><Link href="/register" prefetch={false} className="btn btn-primary">{t("shell.register")}</Link></> : null}
  </div>;
}

export function GlobalHeader({ pathname }: { pathname: string }): ReactElement {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const [confirmingLogout, setConfirmingLogout] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const logoutPending = useRef(false);

  async function confirmLogout() {
    if (logoutPending.current) return;
    logoutPending.current = true;
    setLoggingOut(true);
    try { await logout(); }
    finally {
      setConfirmingLogout(false);
      setLoggingOut(false);
      logoutPending.current = false;
    }
  }

  return <>
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/" className="brand" aria-label={t("shell.brandOverview")}><span className="brand-mark" aria-hidden="true"><AppLogo variant="primary" /></span><strong>IELTS Studio</strong></Link>
        <PrimaryNavigation pathname={pathname} />
        <HeaderActions loggingOut={loggingOut} onLogout={() => setConfirmingLogout(true)} pathname={pathname} />
      </div>
    </header>
    <ConfirmDialog open={confirmingLogout && user !== null} title={t("shell.logoutTitle")} description={t("shell.logoutDescription")} confirmLabel={t("shell.logoutConfirm")} pending={loggingOut} onCancel={() => setConfirmingLogout(false)} onConfirm={() => void confirmLogout()} />
  </>;
}
