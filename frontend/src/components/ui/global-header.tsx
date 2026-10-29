"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactElement, type ReactNode, type RefObject } from "react";
import Link from "next/link";
import { AppLogo } from "./app-logo";
import { ConfirmDialog } from "./confirm-dialog";
import { TRANSFER_ROUTE } from "@/lib/routes";
import { useAuth } from "@/features/auth/auth-provider";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { roleTranslationKeys, translate } from "@/lib/i18n/translations";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { PersonalizationDialog } from "@/features/personalization/personalization-dialog";
import { usePersonalization } from "@/features/personalization/personalization-provider";
import { MoonIcon, SettingsIcon, SunIcon } from "./icons";
import { VietnamClock } from "./vietnam-clock";

const navigation = [
  { message: "shell.home", href: "/" },
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
  { message: "shell.classrooms", href: "/admin/classrooms" },
] as const;
const teacherNavigation = [{ message: "shell.builder", href: "/teacher/tests" }, { message: "shell.classrooms", href: "/teacher/classrooms" }] as const;

function isCurrent(pathname: string, href: string) {
  return href === "/" || href === "/admin" ? pathname === href : pathname.startsWith(href);
}

function CatalogNavigationLink({ href, children, ...props }: { href: string; children: ReactNode; className: string; "aria-current"?: "page" }) {
  const [intent, setIntent] = useState(false);
  function prepare() {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || /^(slow-)?2g$/.test(connection?.effectiveType ?? "")) return;
    setIntent(true);
  }
  return <Link {...props} href={href} prefetch={intent ? null : false} onMouseEnter={prepare} onFocus={prepare}>{children}</Link>;
}

function PrimaryNavigation({ pathname, id, onNavigate }: { pathname: string; id: string; onNavigate(): void }) {
  const { user, loading, sessionError } = useAuth();
  const { t } = useTranslation();
  if (!user || loading || sessionError) return null;
  const visibleNavigation = [...navigation, ...(user.role === "ADMIN" ? adminNavigation : user.role === "TEACHER" ? teacherNavigation : [{ message: "shell.classrooms" as const, href: "/classrooms" }])];
  return (
    <nav id={id} aria-label={t("shell.primary")} className="primary-nav" onClick={(event) => { if ((event.target as HTMLElement).closest("a")) onNavigate(); }}>
      <ul className="primary-nav-list">
        {visibleNavigation.map((item) => {
          const active = isCurrent(pathname, item.href);
          const props = { href: item.href, "aria-current": active ? "page" as const : undefined, className: `primary-nav-link ${active ? "primary-nav-link-active" : ""}` };
          return <li key={item.href}>{item.href === "/library" || item.href === "/practice" ? <CatalogNavigationLink {...props}>{t(item.message)}</CatalogNavigationLink> : <Link {...props} prefetch={item.href === "/" ? undefined : false}>{t(item.message)}</Link>}</li>;
        })}
      </ul>
    </nav>
  );
}

function GuestHomepagePreferences() {
  const { locale, setLocale, appearance, setAppearance } = usePersonalization();
  const { t } = useTranslation();
  const dark = appearance === "DARK";
  const themeLabel = t(dark ? "shell.useLightTheme" : "shell.useDarkTheme");
  return <div className="guest-home-preferences">
    <div className="guest-language-control" role="group" aria-label={t("personalization.language")}>
      <button type="button" lang="vi" aria-pressed={locale === "vi"} onClick={() => setLocale("vi")}>VI</button>
      <button type="button" lang="en" aria-pressed={locale === "en"} onClick={() => setLocale("en")}>EN</button>
    </div>
    <button type="button" className="icon-button guest-theme-control" aria-label={themeLabel} title={themeLabel} onClick={() => setAppearance(dark ? "LIGHT" : "DARK")}>
      {dark ? <SunIcon width={18} height={18} /> : <MoonIcon width={18} height={18} />}
    </button>
  </div>;
}

function AuthLink({ href, message, primary = false, reserveSpace }: { href: string; message: "shell.login" | "shell.register"; primary?: boolean; reserveSpace: boolean }) {
  const { t } = useTranslation();
  return <Link href={href} prefetch={false} className={`btn ${primary ? "btn-primary" : "btn-ghost"}${reserveSpace ? " guest-auth-action" : ""}`}>
    <span>{t(message)}</span>
    {reserveSpace ? (["en", "vi"] as const).map(locale => <span key={locale} className="guest-auth-sizer" aria-hidden="true">{translate(locale, message)}</span>) : null}
  </Link>;
}

function HeaderActions({ loggingOut, onLogout, onPersonalization, settingsButtonRef, pathname }: { loggingOut: boolean; onLogout(): void; onPersonalization(): void; settingsButtonRef: RefObject<HTMLButtonElement | null>; pathname: string }) {
  const { user, loading, sessionError } = useAuth();
  const { t } = useTranslation();
  return <div className="header-actions">
    {!loading && !user && !sessionError && pathname === "/" ? <GuestHomepagePreferences /> : null}
    <VietnamClock />
    {user && !pathname.startsWith("/settings/personalization") ? <button ref={settingsButtonRef} type="button" className="icon-button" aria-label={t("personalization.title")} title={t("personalization.title")} onClick={onPersonalization}><SettingsIcon width="20" height="20" /></button> : null}
    {user ? <NotificationCenter key={user.id} userId={user.id} /> : null}
    {sessionError ? <p role="alert" className="notice">{sessionError}</p> : null}
    {!loading && user ? <><Link href="/profile" prefetch={false} className="auth-user-label"><span className="auth-user-name">{user.display_name}</span><small>{t(roleTranslationKeys[user.role])}</small></Link><button type="button" className="btn btn-ghost" disabled={loggingOut} onClick={onLogout}>{t("shell.logout")}</button></> : !loading && !sessionError ? <><AuthLink href="/login" message="shell.login" reserveSpace={pathname === "/"} /><AuthLink href="/register" message="shell.register" primary reserveSpace={pathname === "/"} /></> : null}
  </div>;
}

function HeaderBar({ pathname, children }: { pathname: string; children: ReactNode }) {
  const { t } = useTranslation();
  const { user, loading, sessionError } = useAuth();
  const hasNavigation = Boolean(user && !loading && !sessionError);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const navigationId = useId();
  const [navigationState, setNavigationState] = useState({ pathname, open: false });
  if (navigationState.pathname !== pathname) setNavigationState({ pathname, open: false });
  const navigationOpen = hasNavigation && navigationState.pathname === pathname && navigationState.open;
  const closeNavigation = useCallback(() => setNavigationState(current => current.open ? { ...current, open: false } : current), []);

  useEffect(() => {
    if (!navigationOpen) return;
    document.getElementById(navigationId)?.querySelector<HTMLAnchorElement>("a")?.focus();
    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      closeNavigation();
      menuButtonRef.current?.focus();
    }
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [navigationOpen, navigationId, closeNavigation]);

  return <header className="app-header" data-navigation-open={navigationOpen} data-has-navigation={hasNavigation}>
    <div className="app-header-inner">
      <Link href="/" className="brand" aria-label={t("shell.brandOverview")}><span className="brand-mark" aria-hidden="true"><AppLogo variant="primary" /></span><strong>BandPilot</strong></Link>
      <PrimaryNavigation pathname={pathname} id={navigationId} onNavigate={closeNavigation} />
      {children}
      {hasNavigation ? <button ref={menuButtonRef} type="button" className="navigation-toggle icon-button" aria-label={t("shell.menu")} aria-expanded={navigationOpen} aria-controls={navigationId} onClick={() => setNavigationState({ pathname, open: !navigationOpen })}><svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d={navigationOpen ? "m6 6 12 12M6 18 18 6" : "M4 6h16M4 12h16M4 18h16"} /></svg></button> : null}
    </div>
  </header>;
}

/** Presentation chooser only: shares the real header layout without notification requests or mutations. */
export function GlobalHeaderPreview() {
  const { user } = useAuth();
  const { t } = useTranslation();
  return <HeaderBar pathname="/attempt/preview"><div className="header-actions"><VietnamClock /><SettingsIcon width={20} height={20} /><span className="auth-user-label"><span className="auth-user-name">{user?.display_name ?? t(roleTranslationKeys.USER)}</span><small>{t(roleTranslationKeys[user?.role ?? "USER"])}</small></span><span className="btn btn-ghost">{t("shell.logout")}</span></div></HeaderBar>;
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
    <HeaderBar pathname={pathname}>
      <HeaderActions loggingOut={loggingOut} onLogout={() => setConfirmingLogout(true)} onPersonalization={() => setPersonalizationOpen(true)} settingsButtonRef={settingsButtonRef} pathname={pathname} />
    </HeaderBar>
    <ConfirmDialog open={confirmingLogout && user !== null} title={t("shell.logoutTitle")} description={t("shell.logoutDescription")} confirmLabel={t("shell.logoutConfirm")} pending={loggingOut} onCancel={() => setConfirmingLogout(false)} onConfirm={() => void confirmLogout()} />
    <PersonalizationDialog open={personalizationOpen && user !== null} onClose={closePersonalization} returnFocusRef={settingsButtonRef} />
  </>;
}
