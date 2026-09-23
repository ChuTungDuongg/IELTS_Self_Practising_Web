import Link from "next/link";
import { PageHeading } from "@/components/ui/page-heading";
import { getAdminStats, getAdminUsers } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";
import { formatProjectDateTime } from "@/lib/date-time";

export const dynamic = "force-dynamic";

export default async function AdminDashboardPage({ searchParams }: { searchParams: Promise<{ search?: string }> }) {
  const search = (await searchParams).search?.trim() ?? "";
  const [stats, users] = await Promise.all([
    getAdminStats(serverApiRequest).catch(() => null),
    getAdminUsers(search, serverApiRequest).catch(() => null),
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
    <section className="admin-users surface-card">
      <div className="section-header"><div><h2 className="section-title">Users</h2><p className="section-description">{users?.total ?? 0} accounts</p></div><form><label className="library-search"><span className="sr-only">Search users</span><input name="search" defaultValue={search} placeholder="Search email or name" /></label><button className="btn btn-secondary" type="submit">Search</button></form></div>
      {users?.items.length ? <div className="admin-user-list">{users.items.map((user) => <Link key={user.id} href={`/admin/users/${user.id}`} className="admin-user-row"><span><strong>{user.display_name}</strong><small>{user.email}</small></span><span>{user.role}</span><span>{user.attempt_count} attempts</span><span>{user.last_activity_at ? formatProjectDateTime(user.last_activity_at) : "No activity"}</span></Link>)}</div> : <p className="notice">No users match this search.</p>}
    </section>
  </>;
}

function AdminMetric({ label, value }: { label: string; value: string | number }) {
  return <article className="analytics-metric"><span>{label}</span><strong>{value}</strong></article>;
}
