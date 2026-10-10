import { OverviewContent } from "@/components/home/overview-content";
import { getHistory } from "@/lib/api/history";
import { getTests } from "@/lib/api/tests";
import { serverApiRequest } from "@/lib/api/server-client";
import { getAdminStats } from "@/lib/api/admin";
import { userSchema } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const [tests, history, user] = await Promise.all([
    getTests(undefined, serverApiRequest).catch(() => []),
    getHistory(serverApiRequest).catch(() => ({ items: [], groups: [], total: 0 })),
    getHomepageUser(),
  ]);
  const [adminStats, profile] = await Promise.all([
    user?.role === "ADMIN" ? getAdminStats(serverApiRequest) : null,
    user ? getHomepageProfile() : null,
  ]);
  const published = tests.flatMap((test) => test.versions).filter((item) => item.status === "PUBLISHED");
  const inProgress = history.items.filter((item) => item.status === "IN_PROGRESS" || item.status === "PAUSED");
  return <OverviewContent publishedCount={published.length} resumableCount={inProgress.length} testCount={tests.length} isAdmin={user?.role === "ADMIN"} adminStats={adminStats} profile={profile} />;
}

async function getHomepageProfile() {
  try {
    return await getProfile(serverApiRequest);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

async function getHomepageUser() {
  try {
    return userSchema.parse(await serverApiRequest<unknown>("/auth/me"));
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
