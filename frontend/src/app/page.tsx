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
  try {
    return await loadHomepage();
  } catch (error) {
    if (error instanceof ApiError && error.code === "NETWORK_ERROR") {
      return <OverviewContent publishedCount={0} resumableCount={0} testCount={0} isAdmin={false} adminStats={null} profile={null} signedIn={false} apiUnavailable />;
    }
    throw error;
  }
}

async function loadHomepage() {
  const user = await getHomepageUser();
  const [tests, history, adminStats, profile] = await Promise.all([
    // publicOnly filters test visibility; the API still requires a signed-in user.
    user ? getTests(user.role === "ADMIN" ? undefined : { publicOnly: true }, serverApiRequest) : [],
    user ? getHistory(serverApiRequest).catch((error) => { if (error instanceof ApiError && error.status === 401) return { items: [], groups: [], total: 0 }; throw error; }) : { items: [], groups: [], total: 0 },
    user?.role === "ADMIN" ? getAdminStats(serverApiRequest) : null,
    user ? getHomepageProfile() : null,
  ]);
  const published = tests.flatMap((test) => test.versions).filter((item) => item.status === "PUBLISHED");
  const inProgress = history.items.filter((item) => item.status === "IN_PROGRESS" || item.status === "PAUSED");
  return <OverviewContent publishedCount={published.length} resumableCount={inProgress.length} testCount={tests.length} isAdmin={user?.role === "ADMIN"} adminStats={adminStats} profile={profile} recentAttempt={inProgress[0]} signedIn={user !== null} />;
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
