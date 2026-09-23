import { redirect } from "next/navigation";
import { userSchema } from "@/lib/api/auth";
import { serverApiRequest } from "@/lib/api/server-client";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await serverApiRequest<unknown>("/auth/me").then(userSchema.parse).catch(() => null);
  if (!user) redirect("/login?next=/admin");
  if (user.role !== "ADMIN") return <section className="empty-state"><h1>Forbidden</h1><p>This workspace is available to administrators only.</p></section>;
  return children;
}
