import { notFound } from "next/navigation";
import { getAdminUser } from "@/lib/api/admin";
import { serverApiRequest } from "@/lib/api/server-client";
import { AdminUserDetailContent } from "@/features/auth/admin-content";

export const dynamic = "force-dynamic";

export default async function AdminUserPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  const detail = await getAdminUser(userId, serverApiRequest).catch(() => null);
  if (!detail) notFound();
  return <AdminUserDetailContent detail={detail} />;
}
