"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { useTranslation } from "@/lib/i18n/locale-provider";
import { moduleTranslationKeys, statusTranslationKeys } from "@/lib/i18n/translations";
import type { AdminStats, AdminUserList as AdminUserListData, AdminUserDetail } from "@/lib/api/admin";
import { formatProjectDateTime } from "@/lib/date-time";
import { AdminUserActions } from "./admin-user-actions";
import { AdminUserList } from "./admin-user-list";

export function AdminDashboardContent({ stats, users, search, status, offset }: { stats: AdminStats | null; users: AdminUserListData | null; search: string; status: "active" | "deactivated"; offset: number }): ReactElement {
  const { t } = useTranslation();
  return <>
    <PageHeading eyebrow={t("admin.administration")} title={t("admin.dashboard")} description={t("admin.dashboardDescription")} action={<Link className="btn btn-primary" href="/admin/tests">{t("pages.overview.builderAction")}</Link>} />
    {stats ? <section className="admin-stat-grid" aria-label={t("admin.statistics")}>
      <AdminMetric label={t("admin.registered")} value={stats.total_users} />
      <AdminMetric label={t("admin.withAttempts")} value={stats.users_with_attempts} />
      <AdminMetric label={t("admin.activeAttempts")} value={stats.active_attempts} />
      <AdminMetric label={t("admin.completedAttempts")} value={stats.completed_attempts} />
      <AdminMetric label={t("admin.completedMocks")} value={stats.completed_full_mocks} />
      <AdminMetric label={t("admin.skillCounts")} value={`${stats.attempts_by_skill.LISTENING} / ${stats.attempts_by_skill.READING} / ${stats.attempts_by_skill.WRITING}`} />
    </section> : <p className="notice">{t("admin.statsUnavailable")}</p>}
    {users ? <AdminUserList key={`${status}:${search}:${offset}`} users={users} status={status} search={search} stats={stats} /> : <section className="admin-users surface-card"><p role="alert" className="notice notice-error">{t("admin.usersUnavailable")}</p></section>}
  </>;
}

function AdminMetric({ label, value }: { label: string; value: string | number }) {
  return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>;
}

export function AdminUserDetailContent({ detail }: { detail: AdminUserDetail }): ReactElement {
  const { t } = useTranslation();
  return <>
    <PageHeading eyebrow={t("admin.record")} title={detail.user.display_name} description={`${detail.user.email} · ${t(detail.user.role === "ADMIN" ? "shell.roleAdmin" : "shell.roleUser")} · ${t(detail.user.is_active ? "profile.active" : "profile.inactive")}`} action={<AdminUserActions userId={detail.user.id} role={detail.user.role} isActive={detail.user.is_active} />} />
    <section className="admin-stat-grid"><AdminDetail label={t("admin.attempts")} value={detail.history.total} /><AdminDetail label={t("admin.finalized")} value={detail.analytics.total_finalized_attempts} /><AdminDetail label={t("admin.mocks")} value={detail.analytics.completed_full_mocks} /><AdminDetail label={t("profile.lastLogin")} value={detail.user.last_login_at ? formatProjectDateTime(detail.user.last_login_at) : t("profile.never")} /></section>
    <section className="admin-users surface-card profile-card"><h2 className="section-title">{t("profile.profile")}</h2><div className="profile-grid">
      <ProfileDetail label={t("profile.phone")} value={detail.user.phone_number} />
      <ProfileDetail label={t("profile.birth")} value={detail.user.date_of_birth} />
      <ProfileDetail label={t("profile.country")} value={detail.user.country} />
      <ProfileDetail label={t("profile.city")} value={detail.user.city} />
      <ProfileDetail label={t("profile.occupation")} value={detail.user.occupation} />
      <ProfileDetail label={t("profile.institution")} value={detail.user.institution} />
      <ProfileDetail label={t("profile.overall")} value={detail.user.target_band} />
      <ProfileDetail label={t("admin.targetListening")} value={detail.user.target_listening_band} />
      <ProfileDetail label={t("admin.targetReading")} value={detail.user.target_reading_band} />
      <ProfileDetail label={t("admin.targetWriting")} value={detail.user.target_writing_band} />
      <ProfileDetail label={t("admin.targetSpeaking")} value={detail.user.target_speaking_band} />
      <ProfileDetail label={t("profile.targetDate")} value={detail.user.target_test_date} />
      <ProfileDetail label={t("profile.bio")} value={detail.user.bio} />
    </div></section>
    <section className="admin-users surface-card"><h2 className="section-title">{t("shell.history")}</h2>{detail.history.items.length ? <div className="admin-user-list">{detail.history.items.map((attempt) => <div key={attempt.attempt_id} className="admin-user-row"><span><strong>{attempt.test_title}</strong><small>{t("common.versionNumber", { number: attempt.version_number })}</small></span><span>{t(moduleTranslationKeys[attempt.module])}</span><span>{statusTranslationKeys[attempt.status] ? t(statusTranslationKeys[attempt.status]) : attempt.status}</span><span>{attempt.band_score ?? "—"}</span></div>)}</div> : <p className="notice">{t("admin.noAttempts")}</p>}</section>
  </>;
}

function AdminDetail({ label, value }: { label: string; value: string | number }) {
  return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>;
}

function ProfileDetail({ label, value }: { label: string; value: string | number | null }) {
  const { t } = useTranslation();
  return <div className="profile-detail"><span>{label}</span><strong>{value === null || value === "" ? t("admin.notProvided") : value}</strong></div>;
}
