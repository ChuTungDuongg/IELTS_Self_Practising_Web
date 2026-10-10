import { getAdminStats, getAdminUsers } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";

import { AdminDashboardContent } from "@/features/auth/admin-content";

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
  return <AdminDashboardContent stats={stats} users={users} search={search} status={status} offset={offset} />;
}
