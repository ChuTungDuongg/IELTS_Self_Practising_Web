import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { AdminUserList } from "@/features/auth/admin-user-list";
import { getAdminStats, getAdminUsers } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";

export const dynamic = "force-dynamic";

export default async function AdminDashboardPage({ searchParams }: { searchParams: Promise<{ search?: string; status?: string; offset?: string }> }) {
  const params = await searchParams;
  const search = params.search?.trim() ?? "";
  const status = params.status === "deactivated" ? "deactivated" : "active";
  const parsedOffset = Number(params.offset ?? 0);
  const offset = Number.isSafeInteger(parsedOffset) && parsedOffset >= 0 ? parsedOffset : 0;
  const [stats, users] = await Promise.all([
    getAdminStats(serverApiRequest).catch(() => null),
    getAdminUsers({ search, isActive: status === "active", offset }, serverApiRequest).catch(() => null),
  ]);
  return <>
    <PageHeading eyebrow="Administration" title="Platform dashboard" description="User activity and learning data, with credentials and session secrets excluded." action={<Link className="btn btn-primary" href="/admin/tests">Open Builder</Link>} />
    {stats ? <section className="admin-stat-grid" aria-label="Platform statistics">
      <AdminMetric label="Registered users" value={stats.total_users} />
      <AdminMetric label="Users with attempts" value={stats.users_with_attempts} />
      <AdminMetric label="Active attempts" value={stats.active_attempts} />
      <AdminMetric label="Completed attempts" value={stats.completed_attempts} />
      <AdminMetric label="Completed Full Mocks" value={stats.completed_full_mocks} />
      <AdminMetric label="Listening / Reading / Writing" value={`${stats.attempts_by_skill.LISTENING} / ${stats.attempts_by_skill.READING} / ${stats.attempts_by_skill.WRITING}`} />
    </section> : <p className="notice">Platform statistics are unavailable.</p>}
    {users ? <AdminUserList key={`${status}:${search}:${offset}`} users={users} status={status} search={search} stats={stats} /> : <section className="admin-users surface-card"><p role="alert" className="notice notice-error">Users are unavailable.</p></section>}
  </>;
}

function AdminMetric({ label, value }: { label: string; value: string | number }) {
  return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>;
}
