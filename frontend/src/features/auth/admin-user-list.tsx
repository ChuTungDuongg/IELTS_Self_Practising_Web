"use client";

import type { TranslationKey, TranslationParams } from "@/lib/i18n/types";

import { useTranslation } from "@/lib/i18n/locale-provider";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { deleteAdminUser, updateAdminUser } from "@/lib/api/admin";
import type { AdminStats, AdminUserList as AdminUserListData } from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import { formatProjectDateTime } from "@/lib/date-time";

type AdminUser = AdminUserListData["items"][number];
type UserStatus = "active" | "deactivated";

export function AdminUserList({ users, status, search, stats }: {
  users: AdminUserListData;
  status: UserStatus;
  search: string;
  stats: AdminStats | null;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const [items, setItems] = useState(users.items);
  const [resultTotal, setResultTotal] = useState(users.total);
  const [counts, setCounts] = useState<{ active: number | null; deactivated: number | null }>({
    active: stats?.active_users ?? (status === "active" ? users.total : null),
    deactivated: stats ? stats.total_users - stats.active_users : (status === "deactivated" ? users.total : null),
  });
  const [pendingId, setPendingId] = useState<string | null>(null);
  const pendingRef = useRef(false);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [error, setError] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const errorText = typeof error === "string" ? error : error ? t(error.message, error.params) : null;
  const [success, setSuccess] = useState<string | { message: TranslationKey; params?: TranslationParams } | null>(null);
  const successText = typeof success === "string" ? success : success ? t(success.message, success.params) : null;
  const [serverSnapshot, setServerSnapshot] = useState({ users, stats, status });
  if (serverSnapshot.users !== users || serverSnapshot.stats !== stats || serverSnapshot.status !== status) {
    setServerSnapshot({ users, stats, status });
    setItems(users.items);
    setResultTotal(users.total);
    setCounts({
      active: stats?.active_users ?? (status === "active" ? users.total : null),
      deactivated: stats ? stats.total_users - stats.active_users : (status === "deactivated" ? users.total : null),
    });
  }

  function navigate(nextStatus: UserStatus) {
    if (nextStatus === status) return;
    const query = new URLSearchParams({ status: nextStatus });
    if (search) query.set("search", search);
    router.push(`/admin?${query.toString()}`);
  }

  function navigatePage(offset: number) {
    const query = new URLSearchParams({ status });
    if (search) query.set("search", search);
    if (offset > 0) query.set("offset", String(offset));
    router.push(`/admin?${query.toString()}`);
  }

  async function changeStatus(target: AdminUser, isActive: boolean) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPendingId(target.id);
    setError(null);
    setSuccess(null);
    try {
      await updateAdminUser(target.id, { is_active: isActive });
      setItems((current) => current.filter((item) => item.id !== target.id));
      setResultTotal((current) => Math.max(0, current - 1));
      setCounts((current) => ({
        active: current.active === null ? null : current.active + (isActive ? 1 : -1),
        deactivated: current.deactivated === null ? null : current.deactivated + (isActive ? -1 : 1),
      }));
      setSuccess({ message: isActive ? "admin.reactivatedNamed" : "admin.deactivatedNamed", params: { name: target.display_name } });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "admin.updateFailed" });
    } finally {
      pendingRef.current = false;
      setPendingId(null);
    }
  }

  async function permanentlyDelete() {
    if (!deleteTarget || pendingRef.current) return;
    const target = deleteTarget;
    pendingRef.current = true;
    setPendingId(target.id);
    setError(null);
    setSuccess(null);
    try {
      await deleteAdminUser(target.id);
      setItems((current) => current.filter((item) => item.id !== target.id));
      setResultTotal((current) => Math.max(0, current - 1));
      setCounts((current) => ({
        ...current,
        deactivated: current.deactivated === null ? null : current.deactivated - 1,
      }));
      setDeleteTarget(null);
      setSuccess({ message: "admin.deletedNamed", params: { name: target.display_name } });
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : { message: "admin.deleteFailed" });
    } finally {
      pendingRef.current = false;
      setPendingId(null);
    }
  }

  return <section className="admin-users surface-card">
    <div className="section-header">
      <div><h2 className="section-title">{t("admin.users")}</h2><p className="section-description">{t(status === "active" ? resultTotal === 1 ? "admin.activeAccountCount" : "admin.activeAccountsCount" : resultTotal === 1 ? "admin.deactivatedAccountCount" : "admin.deactivatedAccountsCount", { count: resultTotal })}{search ? t("admin.matching") : ""}</p></div>
      <form role="search" action="/admin" method="get">
        <input type="hidden" name="status" value={status} />
        <label className="library-search"><span className="sr-only">{t("admin.searchUsers")}</span><input name="search" defaultValue={search} placeholder={t("admin.searchPlaceholder")} /></label>
        <button className="btn btn-secondary" type="submit">{t("common.search")}</button>
      </form>
    </div>
    <div className="segmented-control" role="tablist" aria-label={t("admin.userStatus")}>
      <button type="button" role="tab" aria-selected={status === "active"} onClick={() => navigate("active")}>{t("admin.activeUsers")} {counts.active === null ? null : <span>({counts.active})</span>}</button>
      <button type="button" role="tab" aria-selected={status === "deactivated"} onClick={() => navigate("deactivated")}>{t("admin.deactivatedUsers")} {counts.deactivated === null ? null : <span>({counts.deactivated})</span>}</button>
    </div>
    {error && !deleteTarget ? <p role="alert" className="notice notice-error">{errorText}</p> : null}
    {success ? <p role="status" className="notice notice-success">{successText}</p> : null}
    {items.length ? <div className="admin-user-list">{items.map((user) => <div key={user.id} className={`admin-user-row admin-user-management-row ${status === "deactivated" ? "admin-user-row-inactive" : ""}`}>
      <span><Link href={`/admin/users/${user.id}`}><strong>{user.display_name}</strong></Link><small>{user.email}</small>{status === "deactivated" ? <StatusBadge status="DEACTIVATED" label={t("admin.deactivated")} /> : null}</span>
      <span>{t(user.role === "ADMIN" ? "shell.roleAdmin" : "shell.roleUser")}</span>
      <span>{t("admin.attemptCount", { count: user.attempt_count })}</span>
      <span className="admin-user-actions"><small>{user.last_activity_at ? formatProjectDateTime(user.last_activity_at) : t("admin.noActivity")}</small>
        {status === "active" ? <button type="button" className="btn btn-ghost" disabled={pendingId !== null} aria-label={t("admin.deactivateNamed", { name: user.display_name })} onClick={() => void changeStatus(user, false)}>{t("admin.deactivate")}</button>
          : <><button type="button" className="btn btn-secondary" disabled={pendingId !== null} aria-label={t("admin.reactivateNamed", { name: user.display_name })} onClick={() => void changeStatus(user, true)}>{t("admin.reactivate")}</button>
            <button type="button" className="btn btn-danger-ghost" disabled={pendingId !== null} aria-label={t("admin.deleteNamed", { name: user.display_name })} onClick={() => { setError(null); setDeleteTarget(user); }}>{t("common.deletePermanently")}</button></>}
      </span>
    </div>)}</div> : <div className="mt-5"><EmptyState title={users.offset > 0 && resultTotal > 0 ? t("admin.emptyPage") : search ? t("admin.noMatching") : status === "active" ? t("admin.noActive") : t("admin.noDeactivated")} description={users.offset > 0 && resultTotal > 0 ? t("admin.previousHelp") : search ? t("admin.searchHelp") : status === "active" ? t("admin.activeHelp") : t("admin.deactivatedHelp")} /></div>}
    {resultTotal > users.limit || users.offset > 0 ? <nav aria-label={t("admin.userPages")} className="admin-user-pagination">
      <button type="button" className="btn btn-secondary" disabled={pendingId !== null || users.offset === 0} onClick={() => navigatePage(Math.max(0, users.offset - users.limit))}>{t("common.previous")}</button>
      <span>{users.offset >= resultTotal ? t("admin.pageEmpty") : t("admin.pageOf", { number: Math.floor(users.offset / users.limit) + 1, count: Math.ceil(resultTotal / users.limit) })}</span>
      <button type="button" className="btn btn-secondary" disabled={pendingId !== null || users.offset + users.limit >= resultTotal} onClick={() => navigatePage(users.offset + users.limit)}>{t("common.next")}</button>
    </nav> : null}
    <ConfirmDialog
      open={deleteTarget !== null}
      title={t("admin.deleteTitle", { name: deleteTarget?.display_name ?? "" })}
      description={t(deleteTarget?.attempt_count === 1 ? "admin.deleteDescriptionOne" : "admin.deleteDescriptionMany", { count: deleteTarget?.attempt_count ?? 0 })}
      confirmLabel={t("common.deletePermanently")}
      pending={pendingId !== null}
      errorMessage={deleteTarget ? errorText ?? undefined : undefined}
      onCancel={() => { setDeleteTarget(null); setError(null); }}
      onConfirm={() => void permanentlyDelete()}
    />
  </section>;
}
