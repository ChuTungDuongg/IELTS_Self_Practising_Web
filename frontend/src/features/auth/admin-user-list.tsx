"use client";

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
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
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
      setSuccess(`${isActive ? "Reactivated" : "Deactivated"} ${target.display_name}.`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The user could not be updated.");
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
      setSuccess(`Permanently deleted ${target.display_name}.`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The user could not be permanently deleted.");
    } finally {
      pendingRef.current = false;
      setPendingId(null);
    }
  }

  return <section className="admin-users surface-card">
    <div className="section-header">
      <div><h2 className="section-title">Users</h2><p className="section-description">{resultTotal} {status === "active" ? "active" : "deactivated"} account{resultTotal === 1 ? "" : "s"}{search ? " matching this search" : ""}</p></div>
      <form role="search" action="/admin" method="get">
        <input type="hidden" name="status" value={status} />
        <label className="library-search"><span className="sr-only">Search users</span><input name="search" defaultValue={search} placeholder="Search email or name" /></label>
        <button className="btn btn-secondary" type="submit">Search</button>
      </form>
    </div>
    <div className="segmented-control" role="tablist" aria-label="User status">
      <button type="button" role="tab" aria-selected={status === "active"} onClick={() => navigate("active")}>Active Users {counts.active === null ? null : <span>({counts.active})</span>}</button>
      <button type="button" role="tab" aria-selected={status === "deactivated"} onClick={() => navigate("deactivated")}>Deactivated Users {counts.deactivated === null ? null : <span>({counts.deactivated})</span>}</button>
    </div>
    {error && !deleteTarget ? <p role="alert" className="notice notice-error">{error}</p> : null}
    {success ? <p role="status" className="notice notice-success">{success}</p> : null}
    {items.length ? <div className="admin-user-list">{items.map((user) => <div key={user.id} className={`admin-user-row admin-user-management-row ${status === "deactivated" ? "admin-user-row-inactive" : ""}`}>
      <span><Link href={`/admin/users/${user.id}`}><strong>{user.display_name}</strong></Link><small>{user.email}</small>{status === "deactivated" ? <StatusBadge status="DEACTIVATED" /> : null}</span>
      <span>{user.role}</span>
      <span>{user.attempt_count} attempts</span>
      <span className="admin-user-actions"><small>{user.last_activity_at ? formatProjectDateTime(user.last_activity_at) : "No activity"}</small>
        {status === "active" ? <button type="button" className="btn btn-ghost" disabled={pendingId !== null} aria-label={`Deactivate ${user.display_name}`} onClick={() => void changeStatus(user, false)}>Deactivate</button>
          : <><button type="button" className="btn btn-secondary" disabled={pendingId !== null} aria-label={`Reactivate ${user.display_name}`} onClick={() => void changeStatus(user, true)}>Reactivate</button>
            <button type="button" className="btn btn-danger-ghost" disabled={pendingId !== null} aria-label={`Delete permanently ${user.display_name}`} onClick={() => { setError(null); setDeleteTarget(user); }}>Delete permanently</button></>}
      </span>
    </div>)}</div> : <div className="mt-5"><EmptyState title={users.offset > 0 && resultTotal > 0 ? "No users on this page" : search ? "No matching users" : status === "active" ? "No active users" : "No deactivated users"} description={users.offset > 0 && resultTotal > 0 ? "Open the previous page to see the remaining accounts." : search ? "Try another email or name, or clear the search." : status === "active" ? "Active accounts will appear here." : "Accounts you deactivate will appear here."} /></div>}
    {resultTotal > users.limit || users.offset > 0 ? <nav aria-label="User pages" className="admin-user-pagination">
      <button type="button" className="btn btn-secondary" disabled={pendingId !== null || users.offset === 0} onClick={() => navigatePage(Math.max(0, users.offset - users.limit))}>Previous</button>
      <span>{users.offset >= resultTotal ? "This page is empty" : `Page ${Math.floor(users.offset / users.limit) + 1} of ${Math.ceil(resultTotal / users.limit)}`}</span>
      <button type="button" className="btn btn-secondary" disabled={pendingId !== null || users.offset + users.limit >= resultTotal} onClick={() => navigatePage(users.offset + users.limit)}>Next</button>
    </nav> : null}
    <ConfirmDialog
      open={deleteTarget !== null}
      title={`Delete “${deleteTarget?.display_name ?? ""}” permanently?`}
      description={`This permanently deletes the account and its personal learning data, including ${deleteTarget?.attempt_count ?? 0} attempt${deleteTarget?.attempt_count === 1 ? "" : "s"} and their history. This action cannot be undone.`}
      confirmLabel="Delete permanently"
      pending={pendingId !== null}
      errorMessage={deleteTarget ? error ?? undefined : undefined}
      onCancel={() => { setDeleteTarget(null); setError(null); }}
      onConfirm={() => void permanentlyDelete()}
    />
  </section>;
}
