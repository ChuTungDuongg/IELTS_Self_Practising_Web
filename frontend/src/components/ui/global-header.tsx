"use client";

import { useCallback, useRef, useState, type ReactElement, type RefObject } from "react";
import Link from "next/link";
import { AppLogo } from "./app-logo";
import { ConfirmDialog } from "./confirm-dialog";
import { TRANSFER_ROUTE } from "@/lib/routes";
import { useAuth } from "@/features/auth/auth-provider";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { roleTranslationKeys } from "@/lib/i18n/translations";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { PersonalizationDialog } from "@/features/personalization/personalization-dialog";
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

function HeaderActions({ loggingOut, onLogout, onPersonalization, settingsButtonRef, pathname }: { loggingOut: boolean; onLogout(): void; onPersonalization(): void; settingsButtonRef: RefObject<HTMLButtonElement | null>; pathname: string }) {
  const { user, loading, sessionError } = useAuth();
  const { t } = useTranslation();
  return <div className="header-actions">
    {user && !pathname.startsWith("/settings/personalization") ? <button ref={settingsButtonRef} type="button" className="icon-button" aria-label={t("personalization.title")} title={t("personalization.title")} onClick={onPersonalization}><SettingsIcon width="20" height="20" /></button> : null}
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
  const [personalizationOpen, setPersonalizationOpen] = useState(false);
  const logoutPending = useRef(false);
  const settingsButtonRef = useRef<HTMLButtonElement>(null);
  const closePersonalization = useCallback(() => setPersonalizationOpen(false), []);

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
        <Link href="/" className="brand" aria-label={t("shell.brandOverview")}><span className="brand-mark" aria-hidden="true"><AppLogo variant="primary" /></span><strong>BandPilot</strong></Link>
        <PrimaryNavigation pathname={pathname} />
        <HeaderActions loggingOut={loggingOut} onLogout={() => setConfirmingLogout(true)} onPersonalization={() => setPersonalizationOpen(true)} settingsButtonRef={settingsButtonRef} pathname={pathname} />
      </div>
    </header>
    <ConfirmDialog open={confirmingLogout && user !== null} title={t("shell.logoutTitle")} description={t("shell.logoutDescription")} confirmLabel={t("shell.logoutConfirm")} pending={loggingOut} onCancel={() => setConfirmingLogout(false)} onConfirm={() => void confirmLogout()} />
    <PersonalizationDialog open={personalizationOpen && user !== null} onClose={closePersonalization} returnFocusRef={settingsButtonRef} />
  </>;
}
